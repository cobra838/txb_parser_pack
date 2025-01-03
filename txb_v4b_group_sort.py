import struct
import sys
import os
import argparse
from operator import itemgetter

def unpack_txb(input_txb, output_txt, force_borders=True):
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
        
        # Читаем entries_metadata
        entries_metadata = []
        for i in range(entry_count):
            text_id = struct.unpack('H', infile.read(2))[0]
            dialog_group = struct.unpack('B', infile.read(1))[0]
            text_order = struct.unpack('B', infile.read(1))[0]
            entries_metadata.append({
                'index': i + 1,
                'text_id': text_id,
                'dialog_group': dialog_group,
                'text_order': text_order
            })

        # Читаем оффсеты
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

        # Создаем список для хранения всех записей
        entries = []

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

            # Создаем список меток для вставки тегов
            markers = []

            # Определяем, нужно ли парсить границы
            should_parse = border_count >= 2 or (border_count == 1 and not force_borders) # убрать not

            if should_parse:
                # Читаем все границы
                for _ in range(border_count):
                    start = struct.unpack('H', infile.read(2))[0] - 1
                    end = struct.unpack('H', infile.read(2))[0] - 1
                    # Читаем байты цвета и шрифта
                    color = struct.unpack('B', infile.read(1))[0]
                    font = struct.unpack('B', infile.read(1))[0]
                    infile.read(2)  # Пропускаем оставшиеся два нулевых байта
                    markers.append((start, end, color, font))
            elif border_count == 1:
                # Если одна граница и нет флага - пропускаем её данные
                infile.read(8)  # Пропускаем позиции start и end
                infile.read(4)  # Пропускаем байты цвета, шрифта и нули

            # Сортируем метки по начальной позиции
            if markers:
                markers.sort(key=lambda x: x[0])

                # Преобразуем текст в список символов
                chars = list(text)

                # Вставляем теги с конца, чтобы не сбить позиции
                for start, end, color, font in reversed(markers):
                    chars.insert(end + 1, f'[/c={color};{font}]')
                    chars.insert(start, '[c]')

                text = ''.join(chars)

            # Добавляем запись в список
            entries.append({
                'index': entries_metadata[i]['index'],
                'dialog_group': entries_metadata[i]['dialog_group'],
                'text_order': entries_metadata[i]['text_order'],
                'text': text
            })

            # Пропускаем оставшиеся байты записи
            if i < entry_count - 1:
                next_offset = text_start + offsets[i + 1]
                infile.seek(next_offset)

    # Группируем записи по dialog_group
    grouped_entries = {}
    for entry in entries:
        group = entry['dialog_group']
        if group not in grouped_entries:
            grouped_entries[group] = []
        grouped_entries[group].append(entry)

    # Сортируем каждую группу по text_order
    for group in grouped_entries:
        grouped_entries[group].sort(key=itemgetter('text_order'))

    # Сортируем группы по первому индексу в каждой группе
    sorted_groups = sorted(grouped_entries.items(), 
                         key=lambda x: min(entry['index'] for entry in x[1]))

    # Записываем отсортированный результат
    with open(output_txt, 'w', encoding='utf-8', newline='') as outfile:
        for group, group_entries in sorted_groups:
            for entry in group_entries:
                outfile.write(f'[t{entry["index"]}-{hex(entry["dialog_group"])[2:]}]{entry["text"]}[/t{entry["index"]}]\n')

    print(f"Файл {output_txt} успешно создан.")

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
    parser = argparse.ArgumentParser(description='Конвертер TXB файлов')
    parser.add_argument('paths', nargs='+', help='Пути к файлам или папкам')
    parser.add_argument('-b', '--force-borders', action='store_true', help='Принудительно не парсить границы, если их == 1')
    
    args = parser.parse_args()

    try:
        process_files(args.paths, args.force_borders)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
