# тестовый депозит, реальные данные
# точки находит достаточно тупо на 1,5 таймфреймах. На больших не проверял, хотя следовало бы. А почему бы и нет. 
# доделаю бота и запущу на тестовом сервере на пару дней.

import matplotlib.pyplot as plt
import pandas as pd
import requests
import websockets
import asyncio
import json
import time
from time import gmtime, strftime
import numpy as np
import statsmodels.api as sm
import warnings
from binance.um_futures import UMFutures
from config import TG_API,TG_ID,TG_NAME_BOT,key,secret
warnings.filterwarnings("ignore")

symbol = 'radusdt' # по какой паре торгуем
width = 0.6 # Ширина тела свечи
width2 = 0.05 # Ширина хвоста, шпиля
timeout = time.time() + 60*60*12  # время, которое будет работать скрипт
TF = '5m' # таймфрейм
TP = 0.01 # Тейк профит, процент
SL = 0.0035 # Стоп лосс, процент
DEPO = 100 # Депозит
Leverage = 10 # торговое плечо
DEPOSIT = DEPO # лень переписывать
open_position = False # флаг, стоим в позиции или нет
commission_maker = 0.001 # комиссия а вход
comission_taker = 0.002 # комиссия на выхд
name_bot = 'V_2' # версия бота для сообщений в тг
volume = 200 # сколько свечей получить при запросе к бирже
wait_time = 5 # сколько минут ждать для обновления цены с биржи
canal_max = 0.6 # Верх канала
canal_min = 0.4 # Низ канала
corner_short = 20 # Угол наклона шорт
corner_long = -20 # Угол наклона лонг

data_value = 'Настройки бота:\nТаймфрейм - '+str(TF)+'\nТейк профит - '+str(TP)+'\nСтоп лосс - '+str(SL)+'\nНачальный депозит - '+str(DEPO)+'\nПлечо - '+str(Leverage)+'\nНазвание бота - '+str(name_bot)+'\nВерх канала - '+str(canal_max)+'\nНиз канала - '+str(canal_min)+'\nУгол наклона шорт - '+str(corner_short)+'\nУгол наклона лонг - '+str(corner_long)

open_sl = False # флаг на открытые позиции
price_trade = 0
signal_trade = ''
coin_trade = ''
value_trade = 0
coin_mas_10 = []
profit = 0
loss = 0
commission = 0
sost_trading = 'Депозит = '+str(DEPO)+'| Сделки в плюс принесли '+str(profit)+'| Сделки в минус принесли '+str(loss)+'| На комиссию потратил '+str(commission)

client = UMFutures(key=key, secret=secret)

name_log = name_bot+'_log.txt'
def logger(msg):
    f = open(name_log,'a',encoding='utf-8')
    f.write('\n'+time.strftime("%d.%m.%Y | %H:%M:%S | ", time.localtime())+msg)
    f.close()
logger('------------------------------------------------------------')
logger('Бот запущен в работу')
logger(data_value)

# Получите последние 500 свечей по 5 минут для торговой пары, обрабатываем и записывае данные в датафрейм
def get_futures_klines(symbol,TF,volume):
    x = requests.get('https://binance.com/fapi/v1/klines?symbol='+symbol.lower()+'&limit='+str(volume)+'&interval='+TF)
    df=pd.DataFrame(x.json())
    df.columns=['open_time','open','high','low','close','volume','close_time','d1','d2','d3','d4','d5']
    df=df.drop(['d1','d2','d3','d4','d5'],axis=1)
    df['open']=df['open'].astype(float)
    df['high']=df['high'].astype(float)
    df['low']=df['low'].astype(float)
    df['close']=df['close'].astype(float)
    df['volume']=df['volume'].astype(float)
    return(df) # возвращаем датафрейм с подготовленными данными

# Получаем активные монеты на бирже
def get_top_coin():
    data = client.ticker_24hr_price_change()
    change={}
    coin={}
    coin_mas = []
    coin_mas_10 = []
    for i in data:
        change[i['symbol']] = float(i['priceChangePercent'])
    coin = dict(sorted(change.items(), key=lambda item: item[1],reverse=True))
    for key in coin:
        coin_mas.append(key)
    for x,result in enumerate(coin_mas):
        if x==10:
            break
        coin_mas_10.append(result)
    global symbol
    symbol = coin_mas_10[0]
    return coin_mas_10
coin_mas_10 = get_top_coin() # один раз запускаем функцию, чтобы обновить монету, с которой работаем
# Получаем цену, которая сейчас в моменте в монете
def get_symbol_price(symbol):
    price = round(float(client.ticker_price(symbol)['price']),5)
    return price

# определяем размер позиции, на которую должны зайти
def get_trade_volume():
    volume = round(DEPOSIT*Leverage/get_symbol_price(symbol))
    return volume

# -----------------Индикаторы-------------------
# Определяем наклон ценовой линии
def indSlope(series,n):
    array_sl = [j*0 for j in range(n-1)]
    for j in range(n,len(series)+1):
        y = series[j-n:j]
        x = np.array(range(n))
        x_sc = (x - x.min())/(x.max() - x.min())
        y_sc = (y - y.min())/(y.max() - y.min())
        x_sc = sm.add_constant(x_sc)
        model = sm.OLS(y_sc,x_sc)
        results = model.fit()
        array_sl.append(results.params[-1])
    slope_angle = (np.rad2deg(np.arctan(np.array(array_sl))))
    return np.array(slope_angle)

# Индикатор истинного диапазона и среднего значения истинного диапазона
def indATR(source_DF,n):
    df = source_DF.copy()
    df['H-L']=abs(df['high']-df['low'])
    df['H-PC']=abs(df['high']-df['close'].shift(1))
    df['L-PC']=abs(df['low']-df['close'].shift(1))
    df['TR']=df[['H-L','H-PC','L-PC']].max(axis=1,skipna=False)
    df['ATR'] = df['TR'].rolling(n).mean()
    df_temp = df.drop(['H-L','H-PC','L-PC'],axis=1)
    return df_temp

# найти локальный минимум
def isLCC(DF,i):
    df=DF.copy()
    LCC=0
    if df['close'][i]<=df['close'][i+1] and df['close'][i]<=df['close'][i-1] and df['close'][i+1]>df['close'][i-1]:
        #найдено Дно
        LCC = i-1
    return LCC

# найти локальный максимум
def isHCC(DF,i):
    df=DF.copy()
    HCC=0
    if df['close'][i]>=df['close'][i+1] and df['close'][i]>=df['close'][i-1] and df['close'][i+1]<df['close'][i-1]:
        #найдена вершина
        HCC = i
    return HCC

# получить минимум и максимум канала?
def getMaxMinChannel(DF, n):
    maxx=0
    minn=DF['low'].max()
    for i in range (1,n):
        if maxx<DF['high'][len(DF)-i]:
            maxx=DF['high'][len(DF)-i]
        if minn>DF['low'][len(DF)-i]:
            minn=DF['low'][len(DF)-i]
    return(maxx,minn)

# сгенерируйте фрейм данных со всеми необходимыми данными
def PrepareDF(DF):
    ohlc = DF.iloc[:,[0,1,2,3,4,5]]
    ohlc.columns = ["date","open","high","low","close","volume"]
    ohlc=ohlc.set_index('date')
    df = indATR(ohlc,14).reset_index()
    df['slope'] = indSlope(df['close'],5)
    df['channel_max'] = df['high'].rolling(10).max() # определяем верхний уровень канала
    df['channel_min'] = df['low'].rolling(10).min() # определяем нижний уровень канала
    df['position_in_channel'] = (df['close']-df['channel_min']) / (df['channel_max']-df['channel_min']) # сейчас находимся выше середины канала или ниже
    df = df.set_index('date')
    df = df.reset_index()
    return(df)

# анализирует текущее состояние,и говорит - входим в лонг или шорт
def check_if_signal(ohlc):
    prepared_df = PrepareDF(ohlc)
    signal="нет сигнала" # возвращаемый сигнал, лонг или шорт
    i=98 # 99 - текущая свеча, которая не закрыта, 98 - последняя закрытая свеча, нам нужно 97, чтобы проверить, нижняя она или верхняя
    if isHCC(prepared_df,i-1)>0: # если у нас локальный минимум
        if prepared_df['position_in_channel'][i-1]>canal_max: # проверяем, прижаты ли мы к нижней границе канала
            if prepared_df['slope'][i-1]>corner_short: # смотрим, какой у нас наклон графика
                signal='short'
    if isLCC(prepared_df,i-1)>0: # если у нас локальный максимум
        if prepared_df['position_in_channel'][i-1]<canal_min: # проверяем, прижаты ли мы к верхней границе канала
            if prepared_df['slope'][i-1]<corner_long: # смотрим, какой наклон графика
                signal='long'
    return signal

# -------------------------------- КОНЕЦ ИНДИКАТОРЫ --------------------------------
# -------------------------------- НАЧАЛО ТОРГОВЛЯ --------------------------------
# открывает лонг или шорт
def open_position(trend,value,symbol):
    global open_sl
    global price_trade
    global signal_trade
    global coin_trade
    global value_trade
    global take_profit_price
    global stop_loss_price
    price_trade = get_symbol_price(symbol)
    signal_trade = trend
    coin_trade = symbol
    value_trade = value
    open_sl = True
    take_profit_price = get_take_profit(trend,price_trade) # получаем цену тэйк профита
    stop_loss_price = get_stop_loss(trend,price_trade) # получаем цену стоп лосса
    logger(f'Новая сделка. Монета - {symbol} | Зашли в {trend} | Цена входа - {price_trade}')
    prt(f'🚀 -----Сделка----- 🚀\nБот - {name_bot}\nМонета - {symbol}\nЗашли в {trend}\nЦена входа - {price_trade}')
   

def get_take_profit(trend,price_trade): # получаем цену тейк профита в зависимости от направления
    if trend == 'long':
        return price_trade*(1+TP)
    if trend == 'short':
        return price_trade*(1-TP)
def get_stop_loss(trend,price_trade): # получаем цену стоп лосса в зависимости от направления
    if trend == 'long':
        return price_trade*(1-SL)
    if trend == 'short':
        return price_trade*(1+SL)

# отправляет сообщение в бота и принтует в консоль
def prt(message):
    # print(message)
    url = 'https://api.telegram.org/bot{}/sendMessage'.format(TG_API)
    data = {
        'chat_id': TG_ID,
        'text': message
    }
    response = requests.post(url, data=data)

def check_trade(price):
    now_price_trade = price #получаем текущую цену монеты
    if signal_trade == 'long':
        if float(now_price_trade)>float(take_profit_price):
            close_trade('+',TP)
            return 1
        if float(now_price_trade)<float(stop_loss_price):
            close_trade('-',SL)
            return 1
    if signal_trade == 'short':
        if float(now_price_trade)<float(take_profit_price):
            close_trade('+',TP)
            return 1
        if float(now_price_trade)>float(stop_loss_price):
            close_trade('-',SL)
            return 1
    
prt(f'Робот {name_bot} запущен!\nНастройки:\nТейк профит - {TP*100}%\nСтоп лосс - {SL*100}%\nДепозит - {DEPO}$\nПлечо - {Leverage}\nКомиссия покупка - {commission_maker*100}%\nКомиссия продажа - {comission_taker*100}%\nНачали работать с монетой - {symbol.lower()}')

    
# Закрываем сделку
def close_trade(status,procent):
    global DEPO
    global open_sl
    global profit
    global loss
    global commission
    if status == '+': # если закрыли в плюс
        profit = profit + Leverage*DEPO*procent
        commission = commission + Leverage*DEPO*(commission_maker+comission_taker)
        DEPO = DEPO + Leverage*DEPO*procent - Leverage*DEPO*(commission_maker+comission_taker) # обновляем размер депо
        logger(f'Сработал тейк! Закрылись в плюс, депо = {DEPO} Прибыль = {profit} Комиссия = {commission}')
        prt(f'{name_bot} - Сработал тейк!\nЗакрылись в плюс, депо = {DEPO}\nПрибыль = {profit}\nКомиссия = {commission}')
        open_sl = False
    if status == '-': # если закрыли в минус
        loss = loss + Leverage*DEPO*procent
        commission = commission + Leverage*DEPO*(commission_maker+comission_taker)
        DEPO = DEPO - Leverage*DEPO*procent - Leverage*DEPO*(commission_maker+comission_taker) # обновляем размер депо
        logger(f'Сработал стоп! Закрылись в минус, депо = {DEPO} Убыток = {loss} Комиссия = {commission}')
        prt(f'{name_bot} - Сработал стоп!\nЗакрылись в минус, депо = {DEPO}\nУбыток = {loss}\nКомиссия = {commission}')
        time.sleep(wait_time*60*2) # Интервал в wait_time * 2 минут после стопа, чтобы в эту же позицию по сигналу не зайти
        open_sl = False

    
async def websocket_trade():
    url = 'wss://stream.binance.com:9443/stream?streams='+symbol.lower()+'@miniTicker'
    async with websockets.connect(url) as client: #асинхронно открываем соединение, называем его клиентом, после выхода из контекста функции, закрываем соединение
        while True:
            data = json.loads(await client.recv())['data']
            #prt(data['c'])
            if check_trade(data['c']): # следим за монетой, отрабатываем тп и сл
                break
            
            
                

# -------------------------------- КОНЕЦ ТОРГОВЛЯ --------------------------------
# ------------------------------бесконечный цикл, в котором крутится приложение------------------------------


while True:
    try:     
        if open_sl == False:
            for x,result in enumerate(coin_mas_10):
                prices = get_futures_klines(result,TF,volume)
                trend = check_if_signal(prices)
                time.sleep(5) # Интервал в 10 секунд, чтобы бинанс не долбить
                if trend != 'нет сигнала':
                    break
            if trend == "нет сигнала":
                logger('Нет сигнала')
                print(time.strftime("%d.%m.%Y г. %H:%M", time.localtime()) + ' - Нет сигнала')
                time.sleep(wait_time*60) # Интервал в wait_time минут между каждым новым выполнением, если нет сигнала
            else:
                print('СИГНАЛ!')
                open_position(trend,get_trade_volume(),symbol) # если есть сигнал и мы не стоим в позиции, то открываем позицию
        if open_sl == True:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(websocket_trade())
        if DEPO < 0:
            logger('Бот слил всё депо! Завершили работу бота')
            logger(sost_trading)
            prt(f'Бот {name_bot} слил всё депо! Завершили работу бота') #
            break
        
    except KeyboardInterrupt: #
        
        logger(sost_trading)
        logger('Сбой в работе, остановка')
        prt(f'\nСбой в работе {name_bot}. Остановка.') #
        exit() 
# ------------------------------конец бесконечного цикла------------------------------






