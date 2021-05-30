import argparse
import asyncio
import logging
import os
from functools import partial

import aiofiles
from aiohttp import web
from dotenv import load_dotenv


async def stream_response_archive(request, process, interval_sec, chunk_size):
    response = web.StreamResponse()

    response.headers['Content-Type'] = 'application/zip'
    response.headers['Content-Disposition'] = 'attachment; filename="archive.zip"'

    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)
    try:
        while True:

            if process.stdout.at_eof():
                break
            bin_f = await process.stdout.read(chunk_size)

            # Отправляет клиенту очередную порцию ответа
            logging.debug('Sending archive chunk ...')
            await response.write(bin_f)
            await asyncio.sleep(interval_sec)
    except asyncio.CancelledError:
        logging.debug('Download was interrupted')
        process.kill()
        logging.debug('kill process zip')
        raise
    finally:
        await process.communicate()
    return response


async def archivate(request, interval_sec, folder_path, chunk_size):
    name_photo_directory = request.match_info.get('archive_hash', None)
    directory_path = f"{folder_path}/{name_photo_directory}"
    if not os.path.exists(directory_path):
        logging.debug(f'not folder to path {directory_path}')
        raise web.HTTPNotFound(text='Архив не существует или был удален')

    cmd = ['zip', '-r', '-', name_photo_directory]
    process_zip = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=folder_path,
        stdout=asyncio.subprocess.PIPE)
    return await stream_response_archive(request, process_zip, interval_sec, chunk_size)


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


if __name__ == '__main__':
    load_dotenv()

    interval = os.getenv('INTERVAL_SECS')
    path_to_archive_folder = os.getenv('FOLDER_PATH')
    host = os.getenv('HOST')
    port = os.getenv('PORT')
    size = os.getenv('CHUNK_SIZE')

    parser = argparse.ArgumentParser(description='Service download photo')
    parser.add_argument('-d', '--debug', dest='loglevel', action='store_const', default=logging.INFO,
                        const=logging.DEBUG, help='Enable debug')
    parser.add_argument('-i', '--interval', dest='interval', type=int, default=interval,
                        help=f'Delay in sending a file fragment, default = {interval} sec')
    parser.add_argument('-f', '--folder', dest='folder_path', type=str, default=path_to_archive_folder,
                        help=f'Path to the photo folder, default = {path_to_archive_folder}')
    parser.add_argument('-H', '--host', dest='host', type=str, default=host,
                        help=f'Server ip host, default = {host}')
    parser.add_argument('-P', '--port', dest='port', type=int, default=port,
                        help=f'Server port, default = {port}')
    parser.add_argument('-s', '--size', dest='size', type=int, default=size,
                        help=f'size of the archive chunk to transfer in bytes, default = {size} bytes')

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/',
                partial(archivate, interval_sec=args.interval, folder_path=args.folder_path, chunk_size=args.size)),
    ])
    web.run_app(app, host=args.host, port=args.port)
