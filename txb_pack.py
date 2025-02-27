import struct
import sys
import os
import re

def write_string(file, string):
    """Writes a string to file in UTF-8 format."""
    file.write(string.encode('utf-8'))

def calculate_padding(text_size):
    """Calculates the number of zero-paddings."""
    last_offset_bytes = text_size % 16
    if last_offset_bytes == 0:
        return 4
    elif last_offset_bytes <= 3:
        return 4 - last_offset_bytes
    elif last_offset_bytes <= 7:
        return 8 - last_offset_bytes
    elif last_offset_bytes <= 11:
        return 12 - last_offset_bytes
    else:
        return 16 - last_offset_bytes

def fnv1a_32_hash(text):
    """Calculates FNV1A-32 hash for a string."""
    FNV1A_32_OFFSET = 0x811c9dc5
    FNV1A_32_PRIME = 0x01000193
    
    hash_val = FNV1A_32_OFFSET
    for char in text:
        hash_val ^= ord(char)
        hash_val = (hash_val * FNV1A_32_PRIME) & 0xFFFFFFFF
    return hash_val

def find_border_positions(text):
    """Finds the start and end positions of borders in the text and their content, as well as color and font parameters."""
    borders = []
    pattern = r'\[c\](.*?)\[/c=(\d+);(\d+)\]'

    # Normalize line breaks for uniform processing
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Find all borders in the text
    matches = list(re.finditer(pattern, text, re.DOTALL))
    
    # If there are [c] tags in the text, use their count
    if matches:
        current_pos = 0
        clean_text = ''
        
        for match in matches:
            # Add text before current border
            text_before = text[current_pos:match.start()]
            clean_text_before = re.sub(r'\[\/?c(?:=\d+;\d+)?\]', '', text_before)
            clean_text += clean_text_before
            
            # Add border text
            border_text = match.group(1)
            color = int(match.group(2))
            font = int(match.group(3))
            start_pos = len(clean_text) + 1  # Start position relative to clean_text
            end_pos = start_pos + len(border_text) - 1
            borders.append((start_pos, end_pos, border_text, color, font))
            
            clean_text += border_text
            current_pos = match.end()
        
        # Add remaining text after last border
        text_after = text[current_pos:]
        clean_text += re.sub(r'\[\/?c(?:=\d+;\d+)?\]', '', text_after)
    else:
        clean_text = text
        
    return borders, clean_text

def parse_and_sort_entries(content):
    """Parses and sorts entries from txt file."""
    errors = []
    
    # Normalize line breaks
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    # Split into blocks by headers ([name] or [unknown_hash])
    blocks = []
    lines = content.split('\n')
    current_block = []
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # If we encounter a new header
        if (line.startswith('[') and not line.startswith('[/') and 
            not line.startswith('[c]') and ']' in line):
            
            # Save previous block if it exists
            if current_block:
                blocks.append('\n'.join(current_block))
                current_block = []
            
        # Add current line to block
        current_block.append(lines[i])
        i += 1
    
    # Add last block
    if current_block:
        blocks.append('\n'.join(current_block))
    
    print(f"Number of blocks: {len(blocks)}")

    # Debug information for each block
    for block in blocks:
        print("--- Block Start ---")
        print(block)
        print("--- Block End ---")

    entries = []
    for block in blocks:
        if not block.strip():
            continue
        entry = parse_text_block(block, errors)
        if entry:
            entries.append(entry)
    
    # Sort by index
    entries.sort(key=lambda x: x['sort_index'])
    return entries, errors

def parse_text_block(block, errors=None):
    """Parses individual text block with structure:
    [resource_name]
    b'flags'
    text
    [/tN]
    """
    lines = block.strip().split('\n')
    
    # Debug print for each block
    print("--- Block Start ---")
    print(block)
    print("--- Block End ---")
    
    if len(lines) < 1:
        print("Too few lines")
        if errors is not None:
            errors.append("Too few lines")
        return None

    # First line - resource name
    if not (lines[0].startswith('[') and ']' in lines[0]):
        print("Invalid first line")
        if errors is not None:
            errors.append(f"Invalid first line: {lines[0]}")
        return None
    resource_name = lines[0][1:lines[0].find(']')]

    # Second line - unknown_flags
    if not lines[1].startswith("b'") or not lines[1].endswith("'"):
        print("Invalid flags line")
        if errors is not None:
            errors.append(f"Invalid flags line: {lines[1]}")
        return None

    try:
        flags_hex = lines[1][2:-1].split()
        unknown_flags = bytes([int(x, 16) for x in flags_hex])
    except Exception as e:
        print(f"Error processing flags: {e}")
        if errors is not None:
            errors.append(f"Error processing flags: {e}")
        unknown_flags = b'\x00\x00'

    # Last line - index
    last_line = lines[-1]
    if not last_line.startswith('[/t'):
        print("Invalid index line")
        if errors is not None:
            errors.append(f"Invalid index line: {last_line}")
        return None
    
    try:
        sort_index = int(last_line[3:-1])
    except:
        if errors is not None:
            errors.append(f"Failed to convert index: {last_line}")
        sort_index = 0

    # Text between flags and index
    text_lines = lines[2:-1]
    # Gather text, preserving all line breaks
    text = '\n'.join(text_lines)

    # Calculate hash
    if resource_name.startswith('unknown_'):
        try:
            hex_str = resource_name[8:]
            hash_bytes = bytes.fromhex(hex_str)
            hash_val = struct.unpack('I', hash_bytes)[0]
        except:
            if errors is not None:
                errors.append(f"Failed to process unknown hash: {resource_name}")
            return None
    else:
        hash_val = fnv1a_32_hash(resource_name)

    return {
        'resource_name': resource_name,
        'unknown_flags': unknown_flags,
        'text': text,
        'hash': hash_val,
        'sort_index': sort_index
    }

def pack_txb(input_txt, output_txb):
    """Creates TXB file from text file."""
    # Read and sort text from .txt file
    with open(input_txt, 'r', encoding='utf-8') as txt_file:
        content = txt_file.read()
        entries, _ = parse_and_sort_entries(content)  # Ignore errors as they're already collected

    entry_count = len(entries)
    print(f"Found entries in text file: {entry_count}")

    # Open output file
    with open(output_txb, 'wb') as outfile:
        # Write header
        outfile.write(b'txbL')  # magic
        outfile.write(bytes([0x02, 0x00, 0x00, 0x00]))  # version 2
        size_pos = outfile.tell()
        outfile.write(b'\x00\x00\x00\x00')  # Temporary size
        outfile.write(struct.pack('I', entry_count))

        # Write hashes
        for entry in entries:
            outfile.write(struct.pack('I', entry['hash']))

        # Write temporary zero offsets
        offsets_pos = outfile.tell()
        for _ in range(entry_count):
            outfile.write(b'\x00\x00\x00\x00')

        # Write text entries
        text_data_start = outfile.tell()
        new_offsets = []
        
        for entry in entries:
            new_offsets.append(outfile.tell() - text_data_start)
            borders, clean_text = find_border_positions(entry['text'])
            
            borders_count = len(borders)
            
            char_count = len(clean_text)
            text_size = len(clean_text.encode('utf-8'))
            
            # Write entry header
            outfile.write(struct.pack('hh', char_count, text_size))
            outfile.write(struct.pack('H', borders_count))
            outfile.write(entry['unknown_flags'])  # unknown_flags
            
            # Write text
            write_string(outfile, clean_text)
            
            # Form entry end
            padding_size = calculate_padding(text_size)
            outfile.write(b'\x00' * padding_size)
            
            # Write border information
            for start, end, _, color, font in borders:
                # Write border positions
                outfile.write(struct.pack('HH', start, end))
                # Write color and font from tag
                outfile.write(struct.pack('BB', color, font))
                # Write remaining two bytes
                outfile.write(b'\x00\x00')  # remaining_data

        # Write total size
        final_size = outfile.tell()
        outfile.seek(size_pos)
        outfile.write(struct.pack('I', final_size))
        
        # Write offsets
        outfile.seek(offsets_pos)
        for offset in new_offsets:
            outfile.write(struct.pack('I', offset))

    print(f"File {output_txb} successfully created. File size: {final_size} bytes.")

def process_files(input_paths):
    """Processes files and directories."""
    all_errors = {}
    
    for path in input_paths:
        if os.path.isfile(path) and path.lower().endswith('.txt'):
            output_txb = os.path.splitext(path)[0] + '_new.txb'
            print(f"\nProcessing file: {path}")
            try:
                with open(path, 'r', encoding='utf-8') as txt_file:
                    content = txt_file.read()
                    entries, errors = parse_and_sort_entries(content)
                    if errors:
                        all_errors[path] = errors
                pack_txb(path, output_txb)
            except Exception as e:
                print(f"Error processing {path}: {e}")
                all_errors[path] = [str(e)]
        elif os.path.isdir(path):
            print(f"\nProcessing directory: {path}")
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith('.txt'):
                        input_txt = os.path.join(root, file)
                        output_txb = os.path.splitext(input_txt)[0] + '_new.txb'
                        print(f"\nProcessing file: {input_txt}")
                        try:
                            with open(input_txt, 'r', encoding='utf-8') as txt_file:
                                content = txt_file.read()
                                entries, errors = parse_and_sort_entries(content)
                                if errors:
                                    all_errors[input_txt] = errors
                            pack_txb(input_txt, output_txb)
                        except Exception as e:
                            print(f"Error processing {input_txt}: {e}")
                            all_errors[input_txt] = [str(e)]
    
    # Print error report at the end
    if all_errors:
        print("\n=== ERROR REPORT ===")
        for file_path, errors in all_errors.items():
            print(f"\nErrors in file: {file_path}")
            for error in errors:
                print(f"  - {error}")
        print("=== END OF REPORT ===")

def main():
    if len(sys.argv) < 2:
        print("Usage: python pack_txb.py <path1> [path2 ...]")
        print("Paths can be either .txt files or directories")
        sys.exit(1)
    
    try:
        process_files(sys.argv[1:])
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
