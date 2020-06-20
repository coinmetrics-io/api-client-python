import sys
from datetime import date, timedelta
from multiprocessing import Pool, cpu_count
from os import makedirs, environ
from os.path import join, exists

from coinmetrics.api_client import CoinMetricsClient
from coinmetrics.constants import PagingFrom

EXCHANGES_TO_EXPORT = [
    'binance.us', 'binance', 'coinbase', 'okex', 'kraken', 'huobi', 'bitmex', 'bitfinex', 'deribit',
]

FUTURES_MARKETS_TO_EXPORT = [
    'binance-BTCUSDT-future',
    'bitmex-XBTUSD-future',
    'bitfinex-tBTCF0:USTF0-future',
    'deribit-BTC-PERPETUAL-future'
]

LOCAL_DST_ROOT = '.'
EXPORT_START_DATE = '2020-05-30'
EXPORT_END_DATE = '2020-05-31'
PROCESSED_DAYS_REGISTRY_FILE_PATH = 'processed_days_registry.txt'

api_key = environ.get('CM_API_KEY') or sys.argv[1]  # sys.argv[1] is executed only if CM_API_KEY is not found
client = CoinMetricsClient(api_key)


def export_data():
    min_export_date = date.fromisoformat(EXPORT_START_DATE)
    max_export_date = date.fromisoformat(EXPORT_END_DATE)
    processed_dates_and_markets = read_already_processed_files()

    markets = get_markets_to_process()

    print('getting markets:', [market['market'] for market in markets])

    processes_count = cpu_count() * 2

    with Pool(processes_count) as pool:
        tasks = []
        for market in markets:
            if market['type'] == 'spot':
                instrument_root = '{}_{}_{}'.format(market['base'], market['quote'], market['type'])
            else:
                instrument_root = '{}_{}'.format(market['symbol'].replace(':', '_'), market['type'])
            market_data_root = join(LOCAL_DST_ROOT, market['market'].split('-')[0], instrument_root)
            min_date = max(date.fromisoformat(market['min_time'].split('T')[0]), min_export_date)
            max_date = min(date.fromisoformat(market['max_time'].split('T')[0]), max_export_date)
            makedirs(market_data_root, exist_ok=True)

            for target_date_index in range((max_date - min_date).days + 1):
                target_date = min_date + timedelta(days=target_date_index)
                if get_registry_key(market, target_date) not in processed_dates_and_markets:
                    tasks.append(pool.apply_async(export_data_for_a_market,
                                                  (market, market_data_root, target_date)))

        for task in tasks:
            task.get()


def get_markets_to_process():
    markets = []
    for exchange in EXCHANGES_TO_EXPORT:
        for market in client.catalog_markets(exchange=exchange):
            if (market['market'] in FUTURES_MARKETS_TO_EXPORT or
                    (market['type'] == 'spot' and ((market['base'] == 'btc' and market['quote'] in ['usd', 'usdt']) or
                                                   (market['quote'] == 'btc' and market['base'] in ['usd', 'usdt'])))):
                markets.append(market)
    return markets


def read_already_processed_files():
    if exists(PROCESSED_DAYS_REGISTRY_FILE_PATH):
        with open(PROCESSED_DAYS_REGISTRY_FILE_PATH) as registry_file:
            return set(registry_file.read().splitlines())
    return set()


def export_data_for_a_market(market, market_data_root, target_date):
    market_trades = client.get_market_trades(market['market'], start_time=target_date, end_time=target_date,
                                             page_size=10000, paging_from=PagingFrom.START)
    dst_csv_file_path = join(market_data_root, target_date.isoformat()) + '.csv'
    print('downloading data to:', dst_csv_file_path)
    market_trades.export_to_csv(dst_csv_file_path)
    with open(PROCESSED_DAYS_REGISTRY_FILE_PATH, 'a') as registry_file:
        registry_file.write(get_registry_key(market, target_date))


def get_registry_key(market, target_date):
    return '{},{}'.format(market, target_date.isoformat())


if __name__ == '__main__':
    export_data()
