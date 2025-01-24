import pandas as pd
from datetime import datetime, timedelta
import os
import telebot
from telebot.apihelper import ApiTelegramException
import schedule
import time
import yfinance as yf  # Импорт библиотеки yfinance

# Конфигурация Telegram бота
TELEGRAM_BOT_TOKEN = "7651057081:AAE3IDL5Bj8GvfElCJCTWlZ5X_GXgGAWBm8"
TELEGRAM_CHAT_ID = "-1002372860219"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Список тикеров для обработки
TICKERS = ["PEPE24478-USD", "FARTCOIN-USD", "DOGE-USD", "XRP-USD", "SOL-USD", "TRUMP-OFFICIAL-USD"]
TICKER_MAPPING = {
    "PEPE24478-USD": "1000PEPE-USDT",
    "FARTCOIN-USD": "FARTCOIN-USDT",
    "DOGE-USD": "DOGE-USDT",
    "XRP-USD": "XRP-USDT",
    "SOL-USD": "SOL-USDT",
    "TRUMP-OFFICIAL-USD": "TRUMP-USDT"
}

# Функция для отправки сообщений в Telegram с обработкой ошибки 429
def send_telegram_message(message):
    max_retries = 3  # Максимальное количество попыток
    retry_delay = 30  # Задержка между попытками (в секундах)

    for attempt in range(max_retries):
        try:
            bot.send_message(TELEGRAM_CHAT_ID, message, parse_mode='HTML')
            break  # Успешная отправка, выходим из цикла
        except ApiTelegramException as e:
            if "Too Many Requests" in str(e):
                print(f"Ошибка 429: Слишком много запросов. Повторная попытка через {retry_delay} секунд...")
                time.sleep(retry_delay)  # Ждем перед повторной попыткой
            else:
                print(f"Ошибка отправки сообщения в Telegram: {e}")
                break
    else:
        print(f"Не удалось отправить сообщение после {max_retries} попыток.")

# Функция для форматирования уведомлений
def format_notification(sheet_name, time, value, ticker):
    ticker_name = TICKER_MAPPING.get(ticker, ticker)  # Получаем правильное название тикера
    notifications = {
        "Покупка": f"🟢 <b>Покупка</b>\nТикер: <b>{ticker_name}</b>\nВремя: {time}\nЦена: {value:.2f}",
        "Продажа": f"🔴 <b>Продажа</b>\nТикер: <b>{ticker_name}</b>\nВремя: {time}\nЦена: {value:.2f}"
    }
    return notifications.get(sheet_name, "")

# Функция для расчета EMA
def calculate_ema(data, period):
    try:
        return data['Close'].ewm(span=period, adjust=False).mean()
    except Exception as e:
        print(f"Ошибка при расчете EMA{period}: {e}")
        return None

# Функция для обработки одного тикера
def process_ticker(ticker):
    try:
        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"Запуск проверки для тикера {ticker} в {current_time}")
        
        # Загрузка данных по тикеру
        data = yf.download(ticker, period="30d", interval="5m")
        
        if data.empty:
            print(f"Данные по тикеру {ticker} не найдены.")
            return

        # Удаление временной зоны из индекса данных
        data.index = data.index.tz_localize(None)

        # Обработка данных
        data.columns = data.columns.droplevel(1)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        filtered_data = data[(data.index >= start_date) & (data.index <= end_date)].copy()

        required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        filtered_data.dropna(subset=required_columns, inplace=True)

        # Расчет EMA
        ema7 = calculate_ema(filtered_data, 7)
        ema14 = calculate_ema(filtered_data, 14)
        
        if ema7 is not None and ema14 is not None:
            filtered_data['EMA7'] = ema7
            filtered_data['EMA14'] = ema14
            filtered_data['Difference'] = filtered_data['EMA14'] - filtered_data['EMA7']

        # Сохранение данных в Excel
        output_file = f"{ticker}.xlsx"
        if os.path.exists(output_file):
            existing_data = pd.read_excel(output_file, sheet_name='Data', index_col=0)
            existing_attention = pd.read_excel(output_file, sheet_name='Внимание')
            existing_cancel = pd.read_excel(output_file, sheet_name='Отмена')
            existing_buy = pd.read_excel(output_file, sheet_name='Покупка')
            existing_sell = pd.read_excel(output_file, sheet_name='Продажа')
        else:
            existing_data = pd.DataFrame()
            existing_attention = pd.DataFrame(columns=['Время', 'Difference'])
            existing_cancel = pd.DataFrame(columns=['Время', 'Difference'])
            existing_buy = pd.DataFrame(columns=['Время', 'Open'])
            existing_sell = pd.DataFrame(columns=['Время', 'Open'])

        # Добавление новых данных
        new_data = filtered_data[~filtered_data.index.isin(existing_data.index)]
        new_rows_count = len(new_data)
        updated_data = pd.concat([existing_data, new_data])
        columns_to_keep = ['Open', 'High', 'Low', 'Close', 'Volume', 'EMA7', 'EMA14', 'Difference']
        updated_data = updated_data[columns_to_keep]

        # Обработка уведомлений
        attention_data = existing_attention.copy()
        cancel_data = existing_cancel.copy()
        buy_data = existing_buy.copy()
        sell_data = existing_sell.copy()

        new_attention_rows = 0
        new_cancel_rows = 0
        new_buy_rows = 0
        new_sell_rows = 0
        analyzing_sale = False

        # Текущее время в UTC+5
        current_time_utc5 = datetime.now() + timedelta(hours=5)

        for i in range(1, len(updated_data)):
            current_diff = updated_data.iloc[i, 7]
            prev_diff = updated_data.iloc[i - 1, 7]
            current_ema7 = updated_data.iloc[i, 5]
            prev_ema7 = updated_data.iloc[i - 1, 5]

            time_with_offset = updated_data.index[i] + timedelta(hours=5)

            # Пропускаем строки, которые старше текущего времени (UTC+5)
            if time_with_offset <= current_time_utc5:
                continue

            # Логика для листа "Внимание" (без отправки в Telegram)
            if 0 <= current_diff <= 0.20 and current_diff < prev_diff:
                if not attention_data['Время'].eq(time_with_offset).any():
                    new_row = pd.DataFrame({'Время': [time_with_offset], 'Difference': [current_diff]})
                    attention_data = pd.concat([attention_data, new_row], ignore_index=True)
                    new_attention_rows += 1

            # Логика для листа "Отмена" (без отправки в Telegram)
            if current_diff > 0.20 and 0 <= prev_diff <= 0.20:
                if not cancel_data['Время'].eq(time_with_offset).any():
                    new_row = pd.DataFrame({'Время': [time_with_offset], 'Difference': [round(current_diff, 2)]})
                    cancel_data = pd.concat([cancel_data, new_row], ignore_index=True)
                    new_cancel_rows += 1

            # Логика для листа "Покупка" (с отправкой в Telegram)
            if current_diff < 0 and prev_diff > 0:
                if not buy_data['Время'].eq(time_with_offset).any():
                    current_price = updated_data.iloc[i, 0]
                    new_row = pd.DataFrame({'Время': [time_with_offset], 'Open': [current_price]})
                    buy_data = pd.concat([buy_data, new_row], ignore_index=True)
                    new_buy_rows += 1
                    send_telegram_message(format_notification("Покупка", time_with_offset, current_price, ticker))
                    time.sleep(3)  # Задержка между сообщениями

            # Логика для листа "Продажа" (с отправкой в Telegram)
            if current_diff < 0 and prev_diff >= 0:
                analyzing_sale = True
            
            if analyzing_sale and current_ema7 < prev_ema7:
                if not sell_data['Время'].eq(time_with_offset).any():
                    current_price = updated_data.iloc[i, 0]
                    new_row = pd.DataFrame({'Время': [time_with_offset], 'Open': [current_price]})
                    sell_data = pd.concat([sell_data, new_row], ignore_index=True)
                    new_sell_rows += 1
                    send_telegram_message(format_notification("Продажа", time_with_offset, current_price, ticker))
                    time.sleep(3)  # Задержка между сообщениями
                analyzing_sale = False

        # Сохранение данных в Excel
        with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
            updated_data.to_excel(writer, sheet_name='Data', index=True)
            attention_data.to_excel(writer, sheet_name='Внимание', index=False)
            cancel_data.to_excel(writer, sheet_name='Отмена', index=False)
            buy_data.to_excel(writer, sheet_name='Покупка', index=False)
            sell_data.to_excel(writer, sheet_name='Продажа', index=False)
            
            workbook = writer.book
            worksheet_data = writer.sheets['Data']
            number_format = workbook.add_format({'num_format': '0.00'})
            worksheet_data.set_column('A:I', None, number_format)
            
            light_green_format = workbook.add_format({'bg_color': '#C6EFCE'})
            worksheet_data.conditional_format(
                f'I2:I{len(updated_data) + 1}',
                {
                    'type': 'cell',
                    'criteria': '<',
                    'value': 0,
                    'format': light_green_format
                }
            )

            worksheet_data.set_column('A:A', 19)
            worksheet_data.set_column('B:E', 8)
            worksheet_data.set_column('F:F', 13)
            worksheet_data.set_column('G:H', 8)
            worksheet_data.set_column('I:I', 10)

            for sheet_name in ['Внимание', 'Отмена', 'Покупка', 'Продажа']:
                worksheet = writer.sheets[sheet_name]
                worksheet.set_column('A:A', 20)
                worksheet.set_column('B:B', 12, number_format)

        print(f"Файл Excel для тикера {ticker} успешно обновлен.")
        print(f"Количество строк данных: {len(updated_data)}")
        print(f"Добавлено новых строк данных: {new_rows_count}")
        print(f"Добавлено новых строк Внимание: {new_attention_rows}")
        print(f"Добавлено новых строк Отмена: {new_cancel_rows}")
        print(f"Добавлено новых строк Покупка: {new_buy_rows}")
        print(f"Добавлено новых строк Продажа: {new_sell_rows}")

    except Exception as e:
        print(f"\nПроизошла ошибка при обработке тикера {ticker}: {e}")
        send_telegram_message(f"⚠️ <b>Ошибка при обработке тикера {ticker}:</b>\n{str(e)}")

# Основная функция для обработки всех тикеров
def main():
    for ticker in TICKERS:
        process_ticker(ticker)

# Функция для запуска бота по расписанию
def schedule_bot():
    # Указываем минуты, в которые нужно запускать задачу
    minutes_to_run = [2, 3, 7, 8, 12, 13, 17, 18, 22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48, 52, 53, 57, 58]

    for minute in minutes_to_run:
        schedule.every().hour.at(f":{minute:02d}").do(main)
    
    send_telegram_message("🤖 Бот запущен и готов к работе!")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            error_message = f"⚠️ <b>Критическая ошибка в работе бота:</b>\n{str(e)}"
            send_telegram_message(error_message)
            print(f"Критическая ошибка: {e}")
            time.sleep(300)

# Запуск бота
if __name__ == "__main__":
    schedule_bot()
