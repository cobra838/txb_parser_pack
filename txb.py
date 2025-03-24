import struct
import sys
import os
import argparse
from operator import itemgetter
import string

# Constants for FNV1A hash
"""
Idea from: https://github.com/Team-Alua/GR2-txb-extractor
"""
FNV1A_32_OFFSET = 0x811c9dc5
FNV1A_32_PRIME = 0x01000193

def fnv1a_32_hash(text):
    hash_val = FNV1A_32_OFFSET
    for char in text:
        hash_val ^= ord(char)
        hash_val = (hash_val * FNV1A_32_PRIME) & 0xFFFFFFFF
    return hash_val

def generate_dictionary(filename):
    dictionary = {}
    
    with open(r"dict.txt", 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in lines:
            name = line.strip()
            if name:
                dictionary[fnv1a_32_hash(name)] = name
                
    return dictionary

def unpack_txb(input_txb, output_txt, force_borders=True):
    with open(input_txb, 'rb') as infile:
        # Read header
        magic = infile.read(4)
        if magic != b'txbL':
            raise ValueError("Invalid TXB file signature!")

        version = infile.read(4)
        file_size = struct.unpack('I', infile.read(4))[0]
        entry_count = struct.unpack('I', infile.read(4))[0]
        
        # Generate hash dictionary for current file
        name_dictionary = generate_dictionary(os.path.basename(input_txb))
        
        print(f"File version: {version}")
        print(f"File size: {file_size}")
        print(f"Number of entries: {entry_count}")
        
        # Read entries_metadata with hashes
        entries_metadata = []
        for i in range(entry_count):
            text_hash = struct.unpack('I', infile.read(4))[0]
            text_name = name_dictionary.get(text_hash)
            
            if text_name is None:
                hash_bytes = struct.pack('I', text_hash)
                hex_str = ''.join(f'{b:02x}' for b in hash_bytes)
                text_name = f"unknown_{hex_str}"
                # Only for COMICDEMO check letters at the end if we got unknown
                if "COMICDEMO_EPISODE" in os.path.basename(input_txb).upper():
                    for base_name in name_dictionary.values():
                        if base_name[-2:].isdigit():
                            for letter in 'abc':
                                test_name = f"{base_name}{letter}"
                                test_hash = fnv1a_32_hash(test_name)
                                if test_hash == text_hash:
                                    text_name = test_name
                                    break
                        if text_name != f"unknown_{hex_str}":
                            break

            entries_metadata.append({
                'index': i + 1,
                'text_name': text_name,
                'hash': text_hash
            })

        # Read offsets
        offsets = []
        while True:
            value = infile.read(4)
            if len(value) < 4:
                break
            offset = struct.unpack('I', value)[0]
            offsets.append(offset)
            if len(offsets) == entry_count:
                break

        text_start = infile.tell()

        # Create list to store all entries
        entries = []

        # Process each entry
        for i in range(entry_count):
            # Move to entry start
            infile.seek(text_start + offsets[i])

            # Read entry information
            char_count, text_size = struct.unpack('hh', infile.read(4))
            border_count = struct.unpack('h', infile.read(2))[0]
            unknown_flags = infile.read(2)  # Unknown bytes

            # Read text and normalize line breaks
            text = infile.read(text_size).decode('utf-8')
            text = text.replace('\r\n', '\n')  # Normalize CRLF to LF

            # Skip padding zeros
            while True:
                byte = infile.read(1)
                if byte != b'\x00':
                    infile.seek(-1, 1)  # Go back one byte
                    break

            # Create list of markers for tag insertion
            markers = []

            # Determine if borders should be parsed
            should_parse = border_count >= 2 or (border_count == 1 and not force_borders)

            if should_parse:
                # Read all borders
                for _ in range(border_count):
                    start = struct.unpack('H', infile.read(2))[0] - 1
                    end = struct.unpack('H', infile.read(2))[0] - 1
                    color = struct.unpack('B', infile.read(1))[0]
                    font = struct.unpack('B', infile.read(1))[0]
                    infile.read(2)  # Skip remaining two zero bytes
                    markers.append((start, end, color, font))
            elif border_count == 1:
                # If one border and no flag - skip its data
                infile.read(8)  # Skip start and end positions
                infile.read(4)  # Skip color, font and zero bytes

            # Sort markers by start position
            if markers:
                markers.sort(key=lambda x: x[0])

                # Convert text to list of characters
                chars = list(text)

                # Insert tags from end to not mess up positions
                for start, end, color, font in reversed(markers):
                    chars.insert(end + 1, f'[/c={color};{font}]')
                    chars.insert(start, '[c]')

                text = ''.join(chars)

            # Add entry to list
            entries.append({
                'index': i + 1,
                'text': text,
                'unknown_flags': ' '.join(f'{b:02x}' for b in unknown_flags)
            })

            # Skip remaining entry bytes
            if i < entry_count - 1:
                next_offset = text_start + offsets[i + 1]
                infile.seek(next_offset)

        # Sort entries by resource name
        sorted_entries = sorted(entries, key=lambda x: (0, entries_metadata[x['index']-1]['text_name']) if not entries_metadata[x['index']-1]['text_name'].startswith('unknown') else (1, x['index']))
        # Write sorted result
        with open(output_txt, 'w', encoding='utf-8', newline='') as outfile:
            for entry in sorted_entries:
                metadata = entries_metadata[entry['index']-1]
                outfile.write(f'[{metadata["text_name"]}]\nb\'{entry["unknown_flags"]}\'\n{entry["text"]}\n[/t{entry["index"]}]\n\n')

    print(f"File {output_txt} successfully created.")

def process_files(input_paths, force_borders):
    for path in input_paths:
        if os.path.isfile(path) and path.lower().endswith('.txb'):
            output_txt = os.path.splitext(path)[0] + '_new.txt'
            unpack_txb(path, output_txt, force_borders)
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith('.txb'):
                        input_txb = os.path.join(root, file)
                        output_txt = os.path.splitext(input_txb)[0] + '_new.txt'
                        unpack_txb(input_txb, output_txt, force_borders)

def main():
    parser = argparse.ArgumentParser(description='TXB File Converter')
    parser.add_argument('paths', nargs='+', help='Paths to files or folders')
    parser.add_argument('-b', '--force-borders', action='store_true', help='Force not parsing borders if count == 1')
    
    args = parser.parse_args()

    try:
        process_files(args.paths, args.force_borders)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()