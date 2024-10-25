import struct
import sys
import os
import re

def write_string(file, string):
    """Записывает строку в файл в формате UTF-8."""
    file.write(string.encode('utf-8'))

def calculate_padding(text_size):
    """Вычисляет количество нулей-заполнителей."""
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

def find_border_positions(text, original_borders_count):
    """Находит позиции начала и конца границ в тексте и их содержимое, а также параметры цвета и шрифта."""
    borders = []
    pattern = r'\[c\](.*?)\[/c=(\d+);(\d+)\]'
    
    # Нормализуем переводы строк для единообразной обработки
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Ищем все границы в тексте
    matches = list(re.finditer(pattern, text, re.DOTALL))
    
    # Если в тексте есть теги [c], используем их количество
    if matches:
        current_pos = 0
        clean_text = ''
        
        for match in matches:
            # Добавляем текст до текущей границы
            text_before = text[current_pos:match.start()]
            clean_text_before = re.sub(r'\[\/?c(?:=\d+;\d+)?\]', '', text_before)
            clean_text += clean_text_before
            
            # Добавляем текст границы
            border_text = match.group(1)
            color = int(match.group(2))
            font = int(match.group(3))
            start_pos = len(clean_text) + 1  # Позиция начала относительно clean_text
            end_pos = start_pos + len(border_text) - 1
            borders.append((start_pos, end_pos, border_text, color, font))
            
            clean_text += border_text
            current_pos = match.end()
        
        # Добавляем оставшийся текст после последней границы
        text_after = text[current_pos:]
        clean_text += re.sub(r'\[\/?c(?:=\d+;\d+)?\]', '', text_after)
        
        return borders, clean_text
    
    # Если в оригинале одна граница и нет тегов [c], считаем весь текст границей
    elif original_borders_count == 1 and '[c]' not in text:
        return [(1, len(text), text, None, None)], text
    
    # Если границ нет, возвращаем пустой список
    return [], text

def pack_txb(input_txb, input_txt, output_txb):
    # Чтение заголовка и неизвестных данных из оригинального файла
    with open(input_txb, 'rb') as infile:
        magic = infile.read(4)
        if magic != b'txbL':
            raise ValueError("Неверная сигнатура файла TXB!")
        version = infile.read(4)
        original_size = struct.unpack('I', infile.read(4))[0]
        entry_count = struct.unpack('I', infile.read(4))[0]

        print(f"Количество записей в TXB файле: {entry_count}")

        # Чтение неизвестных значений
        unknown_values = [struct.unpack('I', infile.read(4))[0] for _ in range(entry_count)]
        # Чтение старых смещений
        old_offsets = [struct.unpack('I', infile.read(4))[0] for _ in range(entry_count)]
        # Чтение структуры каждой записи
        records_info = []
        start_offset = infile.tell()
        
        # Читаем информацию о записях из оригинального файла
        for i in range(entry_count):
            infile.seek(start_offset + old_offsets[i])
            record_start = infile.read(8)
            borders_count = struct.unpack('H', record_start[4:6])[0]
            unknown_flags = record_start[6:8]
            char_count, text_size = struct.unpack('hh', record_start[:4])
            
            # Пропускаем текст
            infile.seek(text_size, 1)
            
            # Пропускаем padding
            padding_size = calculate_padding(text_size)
            infile.seek(padding_size, 1)
            
            # Читаем данные о границах
            border_data = []
            if borders_count > 0:
                for _ in range(borders_count):
                    border_positions = infile.read(4)
                    # Читаем все 4 байта
                    color_font_data = infile.read(2)  # Первые два байта (цвет и шрифт)
                    remaining_data = infile.read(2)   # Оставшиеся два байта
                    border_data.append((border_positions, color_font_data, remaining_data))
            
            records_info.append((borders_count, unknown_flags, border_data))

    # Чтение текста из файла .txt
    with open(input_txt, 'r', encoding='utf-8') as txt_file:
        content = txt_file.read()
        text_entries = []
        pattern = r'\[t(\d+)\](.*?)\[/t\1\]'
        for match in re.finditer(pattern, content, re.DOTALL):
            text_entries.append(match.group(2))  # Убираем только переносы строк
    print(f"Найдено записей в текстовом файле: {len(text_entries)}")

    if len(text_entries) != entry_count:
        raise ValueError("Количество записей в текстовом файле не соответствует количеству записей в TXB файле!")

    # Открытие выходного файла
    with open(output_txb, 'wb') as outfile:
        # Запись заголовка
        outfile.write(magic)
        outfile.write(version)
        size_pos = outfile.tell()
        outfile.write(b'\x00\x00\x00\x00')  # Временный размер
        outfile.write(struct.pack('I', entry_count))
        # Запись неизвестных значений
        for value in unknown_values:
            outfile.write(struct.pack('I', value))
        # Запись временных нулевых оффсетов
        offsets_pos = outfile.tell()
        for _ in range(entry_count):
            outfile.write(b'\x00\x00\x00\x00')

        # Запись текстовых записей
        text_data_start = outfile.tell()
        new_offsets = []
        
        for i, text in enumerate(text_entries):
            new_offsets.append(outfile.tell() - text_data_start)
            borders, clean_text = find_border_positions(text, records_info[i][0])
            
            borders_count = len(borders)
            
            char_count = len(clean_text)
            text_size = len(clean_text.encode('utf-8'))
            
            # Записываем заголовок записи
            outfile.write(struct.pack('hh', char_count, text_size))
            outfile.write(struct.pack('H', borders_count))  # Записываем актуальное количество границ
            outfile.write(records_info[i][1])  # unknown_flags
            
            # Записываем текст
            write_string(outfile, clean_text)
            
            # Формирование конца записи
            padding_size = calculate_padding(text_size)
            # Заполнение нулями только начиная с конца записи
            outfile.write(b'\x00' * padding_size)
            
            # Записываем информацию о границах
            if borders_count > 0:
                original_border_data = records_info[i][2]
                for j, (start, end, _, color, font) in enumerate(borders):
                    # Записываем позиции границ
                    outfile.write(struct.pack('HH', start, end))
                    
                    if color is not None and font is not None:
                        # Записываем цвет и шрифт из тега
                        outfile.write(struct.pack('BB', color, font))
                        # Записываем оставшиеся два байта из оригинального файла
                        if j < len(original_border_data):
                            outfile.write(original_border_data[j][2])
                        else:
                            outfile.write(b'\x00\x00')
                    else:
                        # Если нет цвета и шрифта в теге, используем данные из оригинального файла
                        if j < len(original_border_data):
                            outfile.write(original_border_data[j][1])  # Записываем цвет и шрифт
                            outfile.write(original_border_data[j][2])  # Записываем оставшиеся два байта
                        else:
                            # Если нет оригинальных данных, используем нули
                            outfile.write(b'\x00\x00\x00\x00')

        # Записываем общий размер
        final_size = outfile.tell()
        # Перезапись пересчитанных данных
        outfile.seek(size_pos)
        outfile.write(struct.pack('I', final_size))
        # Записываем смещения
        outfile.seek(offsets_pos)
        for offset in new_offsets:
            outfile.write(struct.pack('I', offset))

    print(f"Файл {output_txb} успешно создан. Размер файла: {final_size} байт.")

def main():
    if len(sys.argv) != 4:
        print("Использование: python pack_txb.py <входной.txb> <входной.txt> <выходной.txb>")
        sys.exit(1)
    input_txb, input_txt, output_txb = sys.argv[1], sys.argv[2], sys.argv[3]
    if not os.path.isfile(input_txb) or not os.path.isfile(input_txt):
        print("Входные файлы не найдены!")
        sys.exit(1)
    try:
        pack_txb(input_txb, input_txt, output_txb)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
