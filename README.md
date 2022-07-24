# Binance Futures hedging bot
This bot operates in Binance Futures automatically opening and closing hedge positions against a main position
that is always open. Different parameters can be set in order to configure the bot. 

## Parameters
* ``MARKET``: Specifies the market, can be ``COINM`` or ``USDM``
* ``SYMBOL``: Specifies the trading symbol (e.g. ``BTCUSDT``)
* ``SIDE``: Can be ``SHORT`` or ``LONG``
* ``QUANTITY``: Contract size to trade
* ``RESET_ALL``: Whether to reset all, closing previous positions in this symbol
* ``ENTRY_PRICE``: If set, is the entry price for the first limit order. Can be ``None`` and a market order is executed in this case
* ``STOP_LOSS``: Maximum tolerable losses considering trading losses and fees
* ``TAKE_PROFIT``: Price to exit the trade and close all orders
* ``HEDGE_OPEN_PCT``: Percent change (in opposite direction) to open the hedge position (e.g. ``0.001``)
* ``HEDGE_CLOSE_PCT``: Percent change (in main direction) to close the hedge position (e.g ``0.001``)
* ``INITIAL_LOSSES``: Initial losses to consider for total running losses (default ``0``)
* ``MAX_TIME``: Time to fix the Binance Client timestamp to get in sync with the API (default ``86400``) 
* ``TOLERANCE``: Percent tolerance for the Binance Tool helper that creates the orders (default ``0.0005``)

## Features
* It requires [Binance Tools library](https://github.com/AndresRzCh/trading-tools) for helper functions, 
[Binance API Wrapper](https://github.com/sammchardy/python-binance) and 
[Unicorn Binance Websocket API](https://github.com/oliver-zehentleitner/unicorn-binance-websocket-api)
to handle the streams.
* The bot opens a Websocket instance streaming all the filled orders. Then it creates the hedge side order
using Binance API
* When the sum of fees paid and closed positions losses are greater than the ``STOP_LOSS`` parameter or when the 
price of ``SYMBOL`` reaches ``TAKE_PROFIT`` the bot automatically stops.
* Binance API key and Secrey key must be added to environment variables ``BINANCE_API_KEY`` and ``BINANCE_SECRET_KEY``

## Disclaimer
There are no warranties expressed or implied in this repository. I am not responsible for anything done with this program. You assume all responsibility and liability. Use it at your own risk.  

