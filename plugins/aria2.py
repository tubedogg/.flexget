from __future__ import unicode_literals, division, absolute_import
import os
import logging
import re

import urlparse
import xmlrpclib
from flexget import plugin
from flexget.event import event
from flexget.entry import Entry

log = logging.getLogger('aria2')

# TODO: stop using torrent_info_hash[0:16] as the GID

# for RENAME_CONTENT_FILES:
# to rename TV episodes, content_is_episodes must be set to yes
# to rename movies, imdb_lookup must be enabled in the same plugin

class OutputAria2(object):
    def validator(self):
        from flexget import validator
        root = validator.factory()
        root.accept('boolean')
        aria = root.accept('dict')
        aria.accept('text', key='server')
        aria.accept('integer', key='port')
        aria.accept('choice', key='do').accept_choices(['add-new', 'remove-completed'], ignore_case=True)
        aria.accept('text', key='uri')
        aria.accept('boolean', key='exclude_samples')
        aria.accept('boolean', key='exclude_non_content')
        aria.accept('boolean', key='rename_content_files')
        aria.accept('boolean', key='content_is_episodes')
        aria.accept('text', key='rename_template')
        aria.accept('dict', key='file_exts')
        aria.accept('boolean', key='keep_parent_folders')
        aria_config = aria.accept('dict', key='aria_config')
        aria_config.accept_any_key('any')
        return root

    def prepare_config(self, config):
        config.setdefault('server', 'localhost')
        config.setdefault('port', 6800)
        config.setdefault('exclude_samples', False)
        config.setdefault('exclude_non_content', True)
        config.setdefault('rename_content_files', False)
        config.setdefault('content_is_episodes', False)
        config.setdefault('rename_template', '')
        config.setdefault('file_exts', ['.mkv','.avi','.mp4','.wmv','.asf','.divx','.mov','.mpg','.rm'])
        config.setdefault('keep_parent_folders', True)
        return config

    def on_task_output(self, task, config):
        config = self.prepare_config(config)
        if 'do' not in config:
            raise plugin.PluginError('do is required.', log)
        if 'uri' not in config:
            raise plugin.PluginError('uri is required.', log)
        try:
            baseurl = 'http://%s:%s/rpc' % (config['server'], config['port'])
            s = xmlrpclib.ServerProxy(baseurl)
            log.info('Connected to daemon at ' + baseurl + '.')
        except xmlrpclib.Fault as err:
            log.error('XML-RPC fault: Unable to connect to daemon at %s: %s' % (baseurl, err.faultString))
            plugin.PluginError('Could not connect to aria', log)
        except IOError as err:
            log.error('Connection issue with daemon at %s: %s' % (baseurl, err.strerror))
            plugin.PluginError('Could not connect to aria', log)
        except socket.err as err:
            log.error('Socket connection issue with daemon at %s: %s' % (baseurl, err.strerror))
            plugin.PluginError('Could not connect to aria', log)


        # loop entries
        for entry in task.accepted:
            if 'aria_gid' in entry:
                config['aria_config']['gid'] = entry['aria_gid']
            elif 'torrent_info_hash' in entry:
                config['aria_config']['gid'] = entry['torrent_info_hash'][0:16]
            else:
                config['aria_config']['gid'] = ''

            if 'content_files' not in entry:
                if entry['url']:
                    entry['content_files'] = [entry['url']]
                else:
                    entry['content_files'] = [entry['title']]

            counter = 0
            for curFile in entry['content_files']:

                curFilename = curFile.split('/')[-1]

                fileDot = curFilename.rfind(".")
                fileExt = curFilename[fileDot:]

                if len(entry['content_files']) > 1:
                    # if there is more than 1 file, need to give unique gids, this will work up to 999 files
                    counter += 1
                    strCounter = str(counter)
                    if len(entry['content_files']) > 99:
                        # sorry not sorry if you have more than 999 files
                        config['aria_config']['gid'] = config['aria_config']['gid'][0:-3] + strCounter.rjust(3,str('0'))
                    else:
                        config['aria_config']['gid'] = config['aria_config']['gid'][0:-2] + strCounter.rjust(2,str('0'))

                if config['exclude_samples'] == True:
                    # remove sample files from download list
                    if curFilename.lower().find('sample') > -1:
                        continue

                if fileExt not in config['file_exts']:
                    if config['exclude_non_content'] == True:
                        # don't download non-content files, like nfos - definable in file_exts
                        continue
                elif config['rename_content_files'] == True:
                    if config['content_is_episodes']:
                        metainfo_series = plugin.get_plugin_by_name('metainfo_series')
                        guess_series = metainfo_series.instance.guess_series
                        if guess_series(curFilename):
                            parser = guess_series(curFilename)
                            entry['series_name'] = parser.name
                            parser.data = curFilename
                            parser.parse
                            log.debug(parser.id_type)
                            if parser.id_type == 'ep':
                                entry['series_id'] = 'S' + str(parser.season).rjust(2, str('0')) + 'E' + str(parser.episode).rjust(2, str('0'))
                            elif parser.id_type == 'sequence':
                                entry['series_id'] = parser.episode
                            elif parser.id_type and parser.id:
                                entry['series_id'] = parser.id
                        if entry['series_id']:
                            config['aria_config']['out'] = entry.render(config['rename_template']) + fileExt
                            log.verbose(config['aria_config']['out'])
                        elif config['rename_template'].find('series_id') > -1:
                            raise plugin.PluginError('Unable to parse series_id and it is used in rename_template.', log)
                    else:
                        if 'movie_name' not in entry:
                            raise plugin.PluginError('When using rename_content_files with movies, imdb_lookup must be enabled in the task.', log)
                        else:
                            config['aria_config']['out'] = entry.render(config['rename_template']) + fileExt
                            log.verbose(config['aria_config']['out'])
                else:
                    config['aria_config']['out'] = curFilename
                                    
                if config['do'] == 'add-new':
                    newDownload = 0
                    try:
                        r = s.aria2.tellStatus(config['aria_config']['gid'], ['gid', 'status'])
                        log.info('Download status for %s (gid %s): %s' % (entry['title'], r['gid'], r['status']))
                        if r['status'] == 'paused':
                            try:
                                if not task.manager.options.test:
                                    s.aria2.unpause(r['gid'])
                                log.info('  Unpaused download.')
                            except xmlrpclib.Fault as err:
                                raise plugin.PluginError('aria response to unpause request: %s' % err.faultString, log)
                        else:
                            log.info('  Therefore, not re-adding.')
                    except xmlrpclib.Fault as err:
                        if err.faultString[-12:] == 'is not found':
                            newDownload = 1
                        else:
                            raise plugin.PluginError('aria response to download status request: %s' % err.faultString, log)

                    if newDownload == 1:
                        try:
                            entry['filename'] = curFile
                            curUri = entry.render(config['uri'])
                            if not task.manager.options.test:
                                r = s.aria2.addUri([curUri], {key: entry.render(str(value)) for (key, value) in config['aria_config'].iteritems()})
                            else:
                                if config['aria_config']['gid'] == '':
                                    r = '1234567890123456'
                                else:
                                    r = config['aria_config']['gid']
                            log.info('%s successfully added to aria2 with gid %s.' % (config['aria_config']['out'], r))
                            log.verbose('uri: %s' % curUri)
                        except xmlrpclib.Fault as err:
                            raise plugin.PluginError('aria response to add URI request: %s' % err.faultString, log)


                elif config['do'] == 'remove-completed':
                    try:
                        r = s.aria2.tellStatus(config['aria_config']['gid'], ['gid', 'status'])
                        log.info('Status of download with gid %s: %s' % (r['gid'], r['status']))
                        if r['status'] == 'complete' or r['status'] == 'removed':
                            if not task.manager.options.test:
                                try:
                                    a = s.aria2.removeDownloadResult(r['gid'])
                                    if a == 'OK':
                                        log.info('Download with gid %s removed from memory' % r['gid'])
                                except xmlrpclib.Fault as err:
                                    raise plugin.PluginError('aria response to remove request: %s' % err.faultString, log)
                        else:
                            log.info('Download with gid %s could not be removed because of its status: %s' % (r['gid'], r['status']))
                    except xmlrpclib.Fault as err:
                        if err.faultString[-12:] == 'is not found':
                            log.warning('Download with gid %s could not be removed because it was not found. It was possibly previously removed or never added.' % config['aria_config']['gid'])
                        else:
                            raise plugin.PluginError('aria response to status request: %s' % err.faultString, log)


@event('plugin.register')
def register_plugin():
    plugin.register(OutputAria2, 'aria2', api_ver=2)