import struct
import sys
import os

def unpack_txb(input_txb, output_txt):
    with open(input_txb, 'rb') as infile:
        # Читаем заголовок
        magic = infile.read(4)
        if magic != b'txbL':
            raise ValueError("Неверная сигнатура файла TXB!")
        
        version = infile.read(4)
        file_size = struct.unpack('I', infile.read(4))[0]
        entry_count = struct.unpack('I', infile.read(4))[0]
        
        print(f"Версия файла: {version}")
        print(f"Размер файла: {file_size}")
        print(f"Количество записей: {entry_count}")
        
        # Пропускаем неизвестные данные до оффсетов
        unknown_values = []
        while True:
            value = infile.read(4)
            if value == b'\x00\x00\x00\x00':
                break
            unknown_values.append(struct.unpack('I', value)[0])
        
        # Читаем оффсеты
        offsets = [0]  # Первый оффсет уже прочитан (нули)
        for _ in range(entry_count - 1):
            offsets.append(struct.unpack('I', infile.read(4))[0])
        
        text_start = infile.tell()
        
        # Открываем выходной файл
        with open(output_txt, 'w', encoding='utf-8', newline='') as outfile:
            # Обрабатываем каждую запись
            for i in range(entry_count):
                # Переходим к началу записи
                infile.seek(text_start + offsets[i])
                
                # Читаем информацию о записи
                char_count, text_size = struct.unpack('hh', infile.read(4))
                border_count = struct.unpack('h', infile.read(2))[0]
                unknown = infile.read(2)  # Неизвестные байты
                
                # Читаем текст и нормализуем переносы строк
                text = infile.read(text_size).decode('utf-8')
                text = text.replace('\r\n', '\n')  # Нормализуем CRLF в LF
                
                # Пропускаем заполняющие нули
                while True:
                    byte = infile.read(1)
                    if byte != b'\x00':
                        infile.seek(-1, 1)  # Возвращаемся на один байт назад
                        break
                
                # Если есть как минимум две границы, читаем их позиции
                if border_count >= 2:
                    # Создаем список меток для вставки тегов
                    markers = []
                    for _ in range(border_count):
                        start = struct.unpack('H', infile.read(2))[0] - 1
                        end = struct.unpack('H', infile.read(2))[0] - 1
                        # Читаем байты цвета и шрифта
                        color = struct.unpack('B', infile.read(1))[0]
                        font = struct.unpack('B', infile.read(1))[0]
                        infile.read(2)  # Пропускаем оставшиеся два нулевых байта
                        markers.append((start, end, color, font))
                    
                    # Сортируем метки по начальной позиции
                    markers.sort(key=lambda x: x[0])
                    
                    # Преобразуем текст в список символов
                    chars = list(text)
                    
                    # Вставляем теги с конца, чтобы не сбить позиции
                    for start, end, color, font in reversed(markers):
                        chars.insert(end + 1, f'[/c={color};{font}]')
                        chars.insert(start, '[c]')
                    
                    text = ''.join(chars)
                elif border_count == 1:  # Если только одна граница, пропускаем её данные
                    infile.read(8)  # Пропускаем позиции start и end
                    infile.read(4)  # Пропускаем байты цвета, шрифта и нули
                
                # Пропускаем оставшиеся байты записи
                if i < entry_count - 1:
                    next_offset = text_start + offsets[i + 1]
                    infile.seek(next_offset)
                
                # Записываем отформатированный текст
                outfile.write(f'[t{i+1}]{text}[/t{i+1}]\n')
    
    print(f"Файл {output_txt} успешно создан.")

def process_files(input_paths):
    for path in input_paths:
        if os.path.isfile(path) and path.lower().endswith('.txb'):
            output_txt = os.path.splitext(path)[0] + '_new.txt'
            unpack_txb(path, output_txt)
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith('.txb'):
                        input_txb = os.path.join(root, file)
                        output_txt = os.path.splitext(input_txb)[0] + '_new.txt'
                        unpack_txb(input_txb, output_txt)

def main():
    if len(sys.argv) < 2:
        print("Перетащите файлы или папки на скрипт.")
        sys.exit(1)

    input_paths = sys.argv[1:]

    try:
        process_files(input_paths)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
