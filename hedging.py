from unicorn_binance_websocket_api.unicorn_binance_websocket_api_manager import BinanceWebSocketApiManager
from binance.client import Client
import threading
import os
import time
import json
import logging
import pickle
import binancetools


# SETTINGS:
MARKET = 'USDM'
SYMBOL = 'BTCUSDT'
SIDE = 'SHORT'
QUANTITY = 0.5
RESET_ALL = False
ENTRY_PRICE = 69000
STOP_LOSS = 100

# OTHER SETTINGS
TAKE_PROFIT = None
HEDGE_OPEN_PCT = 0.001
HEDGE_CLOSE_PCT = 0.001
INITIAL_LOSSES = 0
MAX_TIME = 24 * 60 * 60
TOLERANCE = 0.0005

# LOGGING:
log_format = '%(levelname)s | %(module)s | %(asctime)s | %(message)s'
log_time = '%d/%m/%Y %H:%M:%S'
log_file_handler = logging.FileHandler('hedging.log')
log_stream = logging.StreamHandler()
log_file_handler.setLevel(logging.DEBUG)
log_stream.setLevel(logging.DEBUG)
logging.basicConfig(format=log_format, datefmt=log_time, handlers=[log_file_handler, log_stream], level=logging.ERROR)
logger = logging.getLogger('hedging')
sockets_logger = logging.getLogger('sockets')
logging.getLogger('sockets').setLevel(logging.DEBUG)
logging.getLogger('hedging').setLevel(logging.DEBUG)
logging.getLogger('binancetools').setLevel(logging.DEBUG)

# INITIAL DEFINITIONS:
client = binancetools.fix_time(Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_SECRET_KEY')))
HEDGE_OPEN_PCT = HEDGE_OPEN_PCT if SIDE == 'LONG' else -HEDGE_OPEN_PCT
HEDGE_CLOSE_PCT = HEDGE_CLOSE_PCT if SIDE == 'LONG' else -HEDGE_CLOSE_PCT
main_direction = {'LONG': 'BUY', 'SHORT': 'SELL'}
hedge_direction = {'LONG': 'SELL', 'SHORT': 'BUY'}
main_side = {'LONG': 'LONG', 'SHORT': 'SHORT'}
hedge_side = {'LONG': 'SHORT', 'SHORT': 'LONG'}
lastcheck = time.time()
open_hedge = 0
close_hedge = 0


def get_fees(market, symbol, size, order, funding=None):

    if funding is None:
        fee = {'USDM': {'LIMIT': 0.00018, 'MARKET': 0.00036}, 'COINM': {'LIMIT': 0.0001, 'MARKET': 0.0005}}
        if market == 'USDM':
            return size * float(client.futures_ticker(symbol=symbol)['lastPrice']) * fee[market][order]
        else:
            return 100 * size * fee[market][order]
    else:
        if market == 'USDM':
            return funding
        else:
            return funding * float(client.futures_coin_ticker(symbol=symbol)[0]['lastPrice'])


def reset_all(fees):
    global RESET_ALL
    logger.debug('Resetting all orders and positions')
    pickle.dump([0, 'SET', 'NONE', 0, 0], open('cache.pickle', 'wb'))
    binancetools.cancel_orders(client, MARKET, SYMBOL)
    executed = binancetools.close_positions(client, MARKET, SYMBOL)
    fees += executed * get_fees(MARKET, SYMBOL, QUANTITY, 'MARKET')
    if ENTRY_PRICE:
        binancetools.create_order(client, MARKET, SYMBOL, main_direction[SIDE], quantity=QUANTITY, limitPrice=ENTRY_PRICE, positionSide=main_side[SIDE], eps=TOLERANCE)
    else:
        binancetools.create_order(client, MARKET, SYMBOL, main_direction[SIDE], quantity=QUANTITY, positionSide=main_side[SIDE], eps=TOLERANCE)
    RESET_ALL = False
    return None


def close_all():
    binancetools.close_positions(client, MARKET, SYMBOL)
    binancetools.cancel_orders(client, MARKET, SYMBOL)
    exit(0)


def try_order(price, direction, tries=5):
    order = None
    for i in range(tries):
        order = binancetools.create_order(client, MARKET, SYMBOL, direction, positionSide=hedge_side[SIDE], stopPrice=price, quantity=QUANTITY, eps=TOLERANCE)
        if order is not None:
            break
    if not order:
        close_all()


def user_callback(socket_manager):
    global lastcheck, client, open_hedge, close_hedge
    while True:
        if socket_manager.is_manager_stopping():
            exit(0)
        msg = socket_manager.pop_stream_data_from_stream_buffer()
        if msg is False:
            time.sleep(0.01)
        else:
            msg = json.loads(msg)
            logger.debug(f'Websocket Message Received: {msg["e"]}')
            losses, entry_status, tp_status, open_hedge, close_hedge = pickle.load(open('cache.pickle', 'rb'))
            logger.debug(f'Reading: {losses}, {entry_status}, {tp_status}')

            if msg['e'] == 'ORDER_TRADE_UPDATE' and msg['o']['s'] == SYMBOL and not RESET_ALL:

                if time.time() - lastcheck > MAX_TIME:
                    client = binancetools.fix_time(Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_SECRET_KEY')))
                    lastcheck = time.time()
                    
                if (msg['o']['ot'] == 'LIMIT' and msg['o']['X'] == 'FILLED' and msg['o']['S'] == hedge_direction[SIDE]) or (losses >= STOP_LOSS):
                    logger.info(f'Process terminated due to Take Profit or Stop Loss order for {SYMBOL} at {MARKET}')
                    close_all()

                if msg['o']['X'] == 'FILLED':

                    if msg['o']['ot'] == 'LIMIT':
                        losses += get_fees(MARKET, SYMBOL, QUANTITY, 'LIMIT')
                    else:
                        losses += get_fees(MARKET, SYMBOL, QUANTITY, 'MARKET')
                        
                    if entry_status == 'SET' and msg['o']['S'] == main_direction[SIDE]:
                        if TAKE_PROFIT:
                            binancetools.create_order(client, MARKET, SYMBOL, hedge_direction[SIDE], quantity=QUANTITY, limitPrice=TAKE_PROFIT, positionSide=main_side[SIDE],
                                                      eps=TOLERANCE)
                            tp_status = 'SET'
                            entry_status = 'COMPLETED'
                        elif not TAKE_PROFIT:
                            entry_status = 'COMPLETED'

                        entry = float(msg['o']['L'])
                        open_hedge = entry * (1 - HEDGE_OPEN_PCT)
                        close_hedge = float(open_hedge) * (1 + HEDGE_CLOSE_PCT)
                        pickle.dump([losses, entry_status, tp_status, open_hedge, close_hedge], open('cache.pickle', 'wb'))
                        logger.debug(f'Saved: {losses}, {entry_status}, {tp_status}, {open_hedge}, {close_hedge}\n')

                    if msg['o']['S'] == hedge_direction[SIDE] and msg['o']['ps'] == hedge_side[SIDE] and entry_status == 'COMPLETED':
                        try_order(close_hedge, main_direction[SIDE], tries=5)
                        logger.debug(f'HEDGE {hedge_side[SIDE]} OPENED @ {msg["o"]["ap"]}. Losses: {losses} USD')

                    elif msg['o']['S'] == main_direction[SIDE] and msg['o']['ps'] == hedge_side[SIDE] and entry_status == 'COMPLETED':
                        pnl = float(msg["o"]["rp"]) * float(msg["o"]["ap"]) if MARKET == 'COINM' else float(msg["o"]["rp"])
                        try_order(open_hedge, hedge_direction[SIDE], tries=5)
                        losses -= pnl
                        logger.debug(f'HEDGE {hedge_side[SIDE]} CLOSED @ {msg["o"]["ap"]}. Profit: {msg["o"]["rp"]} ({pnl} USD). Losses: {losses} USD')

                    elif msg['o']['S'] == main_direction[SIDE] and msg['o']['ps'] == main_side[SIDE] and entry_status == 'COMPLETED':
                        try_order(open_hedge, hedge_direction[SIDE], tries=5)
                        logger.debug(f'HEDGE {hedge_side[SIDE]} SET @ {open_hedge}')

                    pickle.dump([losses, entry_status, tp_status, open_hedge, close_hedge], open('cache.pickle', 'wb'))
                    logger.debug(f'Saved: {losses}, {entry_status}, {tp_status}, {open_hedge}, {close_hedge}\n')

            if msg['e'] == 'ACCOUNT_UPDATE' and msg['a']['m'] == 'FUNDING_FEE':
                funding = 0
                for asset in msg['a']['B']:
                    if SYMBOL.startswith(asset['a']):
                        funding = float(asset['bc'])
                        break
                logger.info(f'Adding Funding Fee of {funding} for {SYMBOL} at {MARKET}')
                losses += get_fees(MARKET, SYMBOL, None, None, funding=funding)
                pickle.dump([losses, entry_status, tp_status, open_hedge, close_hedge], open('cache.pickle', 'wb'))

            if msg['e'] == 'listenKeyExpired':
                initialize_streams()


def initialize_streams():

    logger.info('Starting Websockets')

    if MARKET == 'COINM':
        bsm = BinanceWebSocketApiManager(exchange="binance.com-coin-futures")
    else:
        bsm = BinanceWebSocketApiManager(exchange="binance.com-futures")

    bsm.create_stream(["arr"], ["!userData"], api_key=os.getenv('BINANCE_API_KEY'), api_secret=os.getenv('BINANCE_SECRET_KEY'), stream_label="USER")
    worker_thread = threading.Thread(target=user_callback, args=(bsm,))
    worker_thread.start()


initialize_streams()

# MAIN:
logger.info('Resetting / Fixing initial positions')
if RESET_ALL:
    reset_all(INITIAL_LOSSES)
else:
    cache = pickle.load(open('cache.pickle', 'rb'))
    logger.debug(f'{cache[0]}, {cache[1]}, {cache[2]}')
    if cache[1] == 'COMPLETED' and cache[2] == 'NONE' and TAKE_PROFIT:
        logger.debug('A')
        binancetools.create_order(client, MARKET, SYMBOL, hedge_direction[SIDE], quantity=QUANTITY, limitPrice=TAKE_PROFIT, positionSide=main_side[SIDE], eps=TOLERANCE)
        cache[2] = 'SET'
        pickle.dump(cache, open('cache.pickle', 'wb'))

    orders = binancetools.get_orders(client, MARKET, SYMBOL)
    positions = binancetools.get_positions(client, MARKET, SYMBOL)

    if len(orders) + len(positions) == 0:
        reset_all(INITIAL_LOSSES)
        logger.debug('B1')

    if cache[1] == 'COMPLETED' and ((cache[2] == 'SET' and len(orders) == 1) or (cache[2] == 'NONE' and len(orders) == 0)):
        logger.debug('C')
        if len(positions) == 2:
            binancetools.create_order(client, MARKET, SYMBOL, main_direction[SIDE], quantity=QUANTITY, stopPrice=cache[4], positionSide=hedge_side[SIDE], eps=TOLERANCE)
        elif len(positions) == 1:
            binancetools.create_order(client, MARKET, SYMBOL, hedge_direction[SIDE], quantity=QUANTITY, stopPrice=cache[3], positionSide=hedge_side[SIDE], eps=TOLERANCE)
        else:
            reset_all(INITIAL_LOSSES)
