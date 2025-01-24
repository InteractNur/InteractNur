import os
from pybit.unified_trading import HTTP  # Используем правильный импорт для API Bybit v5
from telethon import TelegramClient, events

# Настройки Bybit (демо-счет)
BYBIT_API_KEY = "BHR3JjbL2fhSFrZVvH"  # Замените на ваш API-ключ для демо-счета
BYBIT_API_SECRET = "QIO0CNq0GFpMSyGEcbuSn7UGJABNcrONenOm"  # Замените на ваш API-секрет для демо-счета
BYBIT_ENDPOINT = "https://api-testnet.bybit.com"  # Демо-сеть Bybit

# Настройки Telegram
TELEGRAM_API_ID = "23201449"  # Ваш API ID (получен на my.telegram.org)
TELEGRAM_API_HASH = "369f147ddb6470ed944a416f1edc91e1"  # Ваш API Hash (получен на my.telegram.org)
TELEGRAM_CHANNEL_ID = "-1002372860219"  # ID вашего канала

# Фиксированная сумма для покупки (в USDT)
FIXED_AMOUNT = 40  # 10 долларов
COMMISSION_RATE = 0.002  # Комиссия 0.2%

# Инициализация сессии Bybit для торговли
session = HTTP(
    testnet=True,  # Используем тестовую сеть
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

# Функция для получения текущей цены актива
def get_current_price(symbol: str):
    try:
        # Получаем данные о тикере
        ticker = session.get_tickers(
            category="linear",  # Для фьючерсных пар
            symbol=symbol
        )
        # Извлекаем последнюю цену
        return float(ticker['result']['list'][0]['lastPrice'])
    except Exception as e:
        print(f"Ошибка при получении цены: {e}")
        return None

# Функция для получения открытой позиции по тикеру
def get_open_position(symbol: str):
    try:
        # Получаем позиции для линейных контрактов
        positions = session.get_positions(
            category="linear",
            symbol=symbol
        )
        
        # Проверяем позиции
        for position in positions['result']['list']:
            if float(position['size']) > 0:
                return float(position['size'])
        return None
    except Exception as e:
        print(f"Ошибка при получении позиции: {e}")
        return None

# Функция для размещения ордера на Bybit
def place_order(symbol: str, side: str, qty: float):
    try:
        # Размещаем ордер для линейных контрактов
        order = session.place_order(
            category="linear",  # Фьючерсные пары
            symbol=symbol,
            side=side,  # "Buy" или "Sell"
            orderType="Market",  # Рыночный ордер
            qty=str(qty),  # Количество как строка
            timeInForce="GoodTillCancel"
        )
        return order
    except Exception as e:
        print(f"Ошибка при размещении ордера: {e}")
        return None

# Функция для расчета количества с учетом комиссии
def calculate_qty_with_commission(amount: float, price: float):
    # Учитываем комиссию 0.2% (0.002)
    return amount / (price * (1 + COMMISSION_RATE))

# Функция для анализа сообщения и извлечения данных
def parse_signal(message: str):
    try:
        # Пример сообщения:
        # 🟢 <b>Покупка</b>\nТикер: <b>BTCUSDT</b>\nВремя: 12:00\nЦена: 50000.00
        lines = message.split("\n")
        action = lines[0].strip()  # 🟢 <b>Покупка</b> или 🔴 <b>Продажа</b>
        ticker = lines[1].split(":")[1].strip().replace("<b>", "").replace("</b>", "")  # BTCUSDT

        # Определяем действие (покупка/продажа)
        if "Покупка" in action:
            side = "Buy"
        elif "Продажа" in action:
            side = "Sell"
        else:
            return None

        return {
            "ticker": ticker,
            "side": side
        }
    except Exception as e:
        print(f"Ошибка при разборе сообщения: {e}")
        return None

# Инициализация Telegram клиента
client = TelegramClient('bybit_bot', TELEGRAM_API_ID, TELEGRAM_API_HASH)

# Обработчик новых сообщений в канале
@client.on(events.NewMessage(chats=TELEGRAM_CHANNEL_ID))
async def handler(event):
    message = event.message.message  # Текст сообщения
    print(f"Новое сообщение: {message}")

    # Парсим сигнал
    signal = parse_signal(message)
    if signal:
        print(f"Сигнал получен: {signal}")

        # Получаем текущую цену актива
        ticker = signal["ticker"]
        current_price = get_current_price(ticker)
        if not current_price:
            print("Не удалось получить текущую цену.")
            return

        if signal["side"] == "Buy":
            # Рассчитываем количество для покупки с учетом комиссии
            qty = calculate_qty_with_commission(FIXED_AMOUNT, current_price)
            print(f"Текущая цена: {current_price}, количество: {qty}")

            # Размещаем ордер на покупку
            result = place_order(ticker, "Buy", qty=qty)
            print(f"Результат размещения ордера: {result}")

        elif signal["side"] == "Sell":
            # Проверяем, есть ли открытая позиция по этому тикеру
            open_position_qty = get_open_position(ticker)
            if open_position_qty:
                # Размещаем ордер на продажу (закрытие позиции)
                result = place_order(ticker, "Sell", qty=open_position_qty)
                print(f"Результат закрытия позиции: {result}")
            else:
                print(f"Позиция по тикеру {ticker} не открыта. Сигнал на продажу пропущен.")
    else:
        print("Не удалось разобрать сигнал или это не сигнал на покупку/продажу.")

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен...")
    with client:
        client.run_until_disconnected()
