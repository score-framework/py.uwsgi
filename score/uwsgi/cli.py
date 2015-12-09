# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.


import click
import json
import score.uwsgi


def parse_alias(alias):
    result = alias.split('/')
    if len(result) == 1:
        result.append(None)
    return result


def zergling_status(zergling):
    status = []
    try:
        if zergling.is_reloading():
            status.append('reloading')
        if zergling.is_paused():
            status.append('paused')
    except score.uwsgi.NotRunning:
        if zergling.is_starting():
            status.append('starting')
        else:
            status.append('stopped')
    return status


@click.group()
@click.argument('conf', type=click.Path(file_okay=True, dir_okay=False))
@click.pass_context
def main(ctx, conf):
    """
    Manages uwsgi processes.
    """
    ctx.obj = score.init.init_from_file(conf)


@main.command('status')
@click.pass_context
def status(ctx):
    for overlord in ctx.obj.uwsgi.Overlord.instances():
        print(overlord.name)
        for zergling in overlord.zerglings():
            status = zergling_status(zergling)
            status = ' (%s)' % ', '.join(status) if status else ''
            print("    %s%s" % (zergling.name, status))


@main.command('spawn-overlord')
@click.argument('name')
@click.pass_context
def spawn_overlord(ctx, name):
    """
    Starts a master server that accepts zerglings.
    """
    overlord = ctx.obj.uwsgi.Overlord(name)
    overlord.regenini()
    overlord.start()


@main.command('slay-overlord')
@click.argument('name')
@click.pass_context
def slay_overlord(ctx, name):
    """
    Stops a previously started master server.
    """
    ctx.obj.uwsgi.Overlord(name).stop()


@main.command('spawn-zergling')
@click.argument('overlord')
@click.argument('file',
                type=click.Path(file_okay=True, dir_okay=False))
@click.option('-e', '--virtualenv',
              type=click.Path(file_okay=False, dir_okay=True, writable=False),
              help="Path to the virtualenv")
@click.option('-p', '--paused', is_flag=True, default=False)
@click.pass_context
def spawn_zergling(ctx, overlord, file, paused, virtualenv=None):
    overlord, name = parse_alias(overlord)
    overlord = ctx.obj.uwsgi.Overlord(overlord)
    zerglings = overlord.zerglings()
    if not name:
        maxname = len(zerglings)
        for zergling in zerglings:
            try:
                maxname = max(maxname, int(zergling.name))
            except ValueError:
                pass
        name = str(maxname + 1)
    try:
        zergling = next(z for z in zerglings if z.name == name)
    except StopIteration:
        zergling = ctx.obj.uwsgi.Zergling(overlord, name, file)
    zergling.regenini(startpaused=paused, virtualenv=virtualenv)
    zergling.start()


@main.command('pause-zergling')
@click.argument('zergling')
@click.pass_context
def pause_zergling(ctx, zergling):
    overlord, zergling = parse_alias(zergling)
    try:
        ctx.obj.uwsgi.Overlord(overlord).zergling(zergling).pause()
    except score.uwsgi.NoSuchZergling:
        raise click.ClickException('No zergling with that name.')
    except score.uwsgi.AlreadyRunning:
        raise click.ClickException('That zergling is already paused')


@main.command('stats-zergling')
@click.argument('zergling')
@click.pass_context
def stats_zergling(ctx, zergling):
    overlord, zergling = parse_alias(zergling)
    try:
        overlord = ctx.obj.uwsgi.Overlord(overlord)
        stats = overlord.zergling(zergling).read_stats()
        print(json.dumps(stats, sort_keys=True, indent=4))
    except score.uwsgi.NoSuchZergling:
        raise click.ClickException('No zergling with that name.')
    except score.uwsgi.NotRunning:
        raise click.ClickException('Zergling not running.')


@main.command('resume-zergling')
@click.argument('zergling')
@click.pass_context
def resume_zergling(ctx, zergling):
    overlord, zergling = parse_alias(zergling)
    try:
        ctx.obj.uwsgi.Overlord(overlord).zergling(zergling).resume()
    except score.uwsgi.NoSuchZergling:
        raise click.ClickException('No zergling with that name.')
    except score.uwsgi.AlreadyRunning:
        raise click.ClickException('That zergling is already running')


@main.command('kill-zergling')
@click.argument('zergling')
@click.pass_context
def kill_zergling(ctx, zergling):
    overlord, zergling = parse_alias(zergling)
    try:
        zergling = ctx.obj.uwsgi.Overlord(overlord).zergling(zergling)
        zergling.stop()
    except score.uwsgi.NoSuchZergling:
        raise click.ClickException('No zergling with that name.')
    except score.uwsgi.NotRunning:
        pass
    zergling.delete()


@main.command('reload-zergling')
@click.argument('zergling')
@click.pass_context
def reload_zergling(ctx, zergling):
    overlord, zergling = parse_alias(zergling)
    try:
        ctx.obj.uwsgi.Overlord(overlord).zergling(zergling).reload()
    except score.uwsgi.NoSuchZergling:
        raise click.ClickException('No zergling with that name.')
    except score.uwsgi.AlreadyReloading:
        raise click.ClickException('That zergling is already reloading')


if __name__ == '__main__':
    main()
