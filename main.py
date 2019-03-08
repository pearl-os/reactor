import os
import threading
import asyncio
import time

from aiohttp import web

from logbook import Logger, StreamHandler
import sys

StreamHandler(sys.stdout).push_application()

from oyster.pacman.repository import *
from oyster.pacman.database import *
from oyster.pacman.chroot import *
from oyster.events import *
from oyster.database import *
from oyster.job import *

async def main():
    logger = Logger('main')

    # repository to push to
    pearl_repo = Repository('pearl-repo', '/repo/pearl/packages', '/repo/pearl/pearl.db.tar.xz')

    # built repository
    pearl_bin = BinaryDatabase('pearl', '/home/reactor/pacman-repo/pacman.conf')

    # For archlinux source repository
    def update_fs(db, directory):
        return False

    def find_package_dirs(db, directory):
        dirs = []
        for f in os.listdir(directory):
            src_x86_path = os.path.join(directory, f, 'repos', 'core-x86_64')
            pkgbuild_x86_path = os.path.join(src_x86_path, 'PKGBUILD')
            if os.path.isdir(src_x86_path) and os.path.exists(pkgbuild_x86_path):
                dirs.append(src_x86_path)
        return dirs

    arch_source = SourceDatabase('archlinux-source', '/home/reactor/packages/archlinux', find_package_dirs)

    # For aur source repository
    def update_fs(db, directory):
        return False

    def find_package_dirs(db, directory):
        dirs = []
        for f in os.listdir(directory):
            path = os.path.join(directory, f)
            pkgbuild = os.path.join(path, 'PKGBUILD')
            if os.path.isdir(path) and os.path.exists(pkgbuild):
                dirs.append(path)
        return dirs

    aur_source = SourceDatabase('aur-source', '/home/reactor/packages/aur', find_package_dirs)

    # Combined source repository
    pearl_src = DerivedDatabase('sources', [arch_source, aur_source])

    # when things are removed from the 
    # source repository, remove them from the pearl repository
    # TODO: This doesn't work if the version just changes
    # pearl_src.add_remove_listener(lambda p: pearl_repo.remove(p.name))

    # Create a build queue
    workers = [ChrootWorker('worker1', '/home/reactor/chroots/worker1',
                                         '/home/reactor/chroots/pacman.conf',
                                         '/repo/pearl/packages',
                                         '/home/reactor/chroots/mkarchroot',
                                         '/home/reactor/chroots/makechrootpkg')]

    def push_results(job, build):
        if build.status != BuildStatus.SUCCESS:
            return

        for f in build.artifacts['binary_files']:
            pearl_repo.add(f)

    # push the results
    # after the worker is done
    for w in workers:
        w.add_listener(push_results)

    event_log = EventLog()

    scheduler = Scheduler(pearl_bin, pearl_src)

    await asyncio.gather(run_website(scheduler, event_log, workers, [ pearl_bin ]),
                         run_scheduler(scheduler, event_log, workers))
    #await run_website(scheduler, event_log, workers, [ pearl_bin ])

async def run_scheduler(scheduler, build_log, workers):
    await scheduler.run(build_log, workers)

async def run_website(scheduler, build_log, workers, databases):
    import oyster.web

    app = oyster.web.make_app(scheduler, build_log, workers, databases)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.run_forever()