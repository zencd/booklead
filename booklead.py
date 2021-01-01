# -*- coding: utf-8 -*-
import argparse
import errno
import hashlib
import json
import os
import random
import shutil
import sys
import time
import urllib.parse

import img2pdf
import requests
from bs4 import BeautifulSoup

DOWNLOADS_DIR = 'downloads'

timeout_btw_requests = 0
downloaded_last_time = False

eshplDl_params = {
    'quality': 8,
    'ext': 'jpg'
}

prlDl_params = {
    'ext': 'jpg'
}

user_agents = [
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.78 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.157 Safari/537.36',
    'Mozilla/5.0 (Windows NT 5.1; rv:7.0.1) Gecko/20100101 Firefox/7.0.1',
    'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:49.0) Gecko/20100101 Firefox/49.0'
]


def to_float(s: str, def_val=0.0):
    try:
        return float(s)
    except ValueError:
        return def_val


def md5_hex(s: str):
    md5 = hashlib.md5()
    md5.update(s.encode('utf-8'))
    return md5.hexdigest()


def makePdf(folder, ext):
    pdf_path = '{}.pdf'.format(folder)
    with open(pdf_path, "wb") as pdf_file:
        img_list = []
        for r, _, f in os.walk(folder):
            for fname in f:
                if not fname.endswith(ext):
                    continue
                img_list.append(os.path.join(r, fname))
        pdf = img2pdf.convert(img_list)
        pdf_file.write(pdf)


def mkdirs_for_regular_file(filename: str):
    """Создаёт все необходимые директории чтобы можно было записать указанный файл"""
    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        try:
            os.makedirs(dirname)
        except OSError as e:  # Guard against race condition
            if e.errno != errno.EEXIST:
                raise


def saveImage(url, img_id, folder, ext):
    global downloaded_last_time, timeout_btw_requests

    image_short = '%05d.%s' % (img_id, ext)
    image_path = os.path.join(DOWNLOADS_DIR, folder, image_short)

    if os.path.exists(image_path) and os.stat(image_path).st_size > 0:
        downloaded_last_time = False
        return False

    mkdirs_for_regular_file(image_path)

    headers = {
        'User-Agent': random.choice(user_agents),
        'Referer': url,
    }

    if downloaded_last_time and timeout_btw_requests:
        time.sleep(timeout_btw_requests)

    downloaded_last_time = True  # перед попыткой скачивания чтобы не нафлудить в случае массовых ошибок
    response = requests.get(url, stream=True, headers=headers)
    if response.ok:
        content_type: str = response.headers.get('content-type')
        if content_type and not content_type.lower().startswith('image/'):
            sys.stdout.write(
                f'\rПредупреждение: кажется, то что скачалось с адреса {url} не является изображением: {content_type}\n')
        with open(image_path, 'wb') as page_file:
            shutil.copyfileobj(response.raw, page_file)
    else:
        sys.stdout.write(f'\rОшибка: не удалось скачать файл {url} - ошибка {response.status_code} {response.reason}\n')
    return True


def eshplDl(url):
    ext = eshplDl_params['ext']
    book_id = md5_hex(url).upper()
    domain = urllib.parse.urlsplit(url).netloc
    quality = eshplDl_params['quality']

    # Обход 429 Too Many Requests 
    headers = {
        'User-Agent': random.choice(user_agents)
    }

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    for script in soup.findAll('script'):
        if 'initDocview' in str(script):
            st = str(script)
            book_json = json.loads(st[st.find('{"'): st.find(')')])
    sys.stdout.write('\nCсылка: {}\n'.format(url))
    sys.stdout.write(' ─ Каталог для загрузки: {}\n'.format(book_id))
    for idx, page in enumerate(book_json['pages']):
        page_url = 'http://{}/pages/{}/zooms/{}'.format(domain, page['id'], quality)
        saveImage(page_url, idx + 1, book_id, ext)
        sys.stdout.write('\r ─ Прогресс: {} из {} стр.'.format(idx + 1, len(book_json['pages'])))
    return book_id, ext


def prlDl(url):
    ext = prlDl_params['ext']

    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    for script in soup.findAll('script'):
        if 'jQuery.extend' in str(script):
            st = str(script)
            book_json = json.loads(st[st.find('{"'): st.find(');')])
            book = book_json['diva']['1']['options']
    response = requests.get(book['objectData'])
    book_data = json.loads(response.text)
    sys.stdout.write('\nCсылка: {}\n'.format(url))
    sys.stdout.write(' ─ Каталог для загрузки: {}\n'.format(book_data['item_title']))
    for idx, page in enumerate(book_data['pgs']):
        page_url = 'https://content.prlib.ru/fcgi-bin/iipsrv.fcgi?FIF={}/{}&WID={}&CVT=jpeg'.format(
            book['imageDir'], page['f'], page['d'][len(page['d']) - 1]['w'])
        saveImage(page_url, idx + 1, book_data['item_title'], ext)
        sys.stdout.write('\r ─ Прогресс: {} из {} стр.'.format(idx + 1, len(book_data['pgs'])))
    return book_data['item_title'], ext


domains = {
    'elib.shpl.ru': eshplDl,
    'docs.historyrussia.org': eshplDl,
    'prlib.ru': prlDl,
    'www.prlib.ru': prlDl,
}


def download_book(url):
    try:
        host = urllib.parse.urlsplit(url)
        if not host.hostname:
            sys.stdout.write(f'\nОшибка: Некорректный урл: {url}')
            return None
        site_downloader = domains.get(host.hostname)
        if not site_downloader:
            sys.stdout.write(f'\nОшибка: Домен {host.hostname} не поддерживается')
            return None
        return site_downloader(url)
    except Exception as e:
        sys.stdout.write(f'\nОшибка: {e}')
        return None


def main(args):
    try:
        urls = []
        if args.timeout:
            global timeout_btw_requests
            timeout_btw_requests = to_float(args.timeout)
        if args.url:
            urls.append(args.url)
        if args.list:
            with open(args.list) as fp:
                line = fp.readline()
                while line:
                    urls.append(line.strip())
                    line = fp.readline()

        sys.stdout.write(f'Ссылок для загрузки - {len(urls)}')

        for url in urls:
            load = download_book(url)
            if load:
                if args.pdf.lower() in ['y', 'yes']:
                    sys.stdout.write('\n ─ Создание PDF...')
                    img_folder_short, img_ext = load
                    img_folder_full = os.path.join(DOWNLOADS_DIR, img_folder_short)
                    makePdf(img_folder_full, img_ext)
    except KeyboardInterrupt:
        sys.stdout.write('\nЗагрузка прервана!')
    except Exception as e:
        sys.stdout.write(f'\nОшибка: {e}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='booklead - Загрузчик книг из интернет-библиотек')
    parser.add_argument('--pdf', dest='pdf', default='', metavar='y', help='Создавать PDF-версии книг')
    parser.add_argument('--list', dest='list', default='', metavar='"list.txt"', help='Файл со списком книг')
    parser.add_argument('--url', dest='url', default='', metavar='"http://..."', help='Ссылка на книгу')
    parser.add_argument('--timeout', dest='timeout', default='0', metavar='1.0',
                        help='Пауза между HTTP-запросами в секундах')
    args = parser.parse_args()
    if args.url or args.list:
        main(args)
    else:
        parser.print_help()
