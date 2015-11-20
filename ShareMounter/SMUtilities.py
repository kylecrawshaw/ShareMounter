#pylint: disable=E0611
from SystemConfiguration import SCDynamicStoreCreate, \
                                SCDynamicStoreCopyValue, \
                                SCDynamicStoreCopyConsoleUser
from Foundation import CFPreferencesCopyAppValue, CFPreferencesAppSynchronize, \
                       CFPreferencesSetAppValue, NSFileManager, NSLog
from AppKit import NSWorkspace, NSUserNotificationCenter, NSUserNotification, \
                   NSURL
import FoundationPlist
import os, subprocess, urlparse
import mount_shares_better
import threading
import PyDialog
from pymacad import kerberos, ad
from Cocoa import NSAppleScript
# import requests

homedir = os.path.expanduser('~')
user_preferences_path = os.path.join(homedir, 'Library/Preferences/ShareMounter.plist')
global_preferences_path = '/Library/Preferences/ShareMounter.plist'
kCFPreferencesCurrentApplication = 'com.github.kylecrawshaw.sharemounter'

class AppleScript(object):

    def __init__(self, osa_script):
        self.script = NSAppleScript.alloc().initWithSource_(osa_script)

    def runScript(self):
        self.script.executeAndReturnError_(None)


def is_ldap_reachable(domain):
    '''Checks whether or not the ldap server can be reached. Returns True.'''
    try:
        cmd = ['dig', '-t', 'srv', '_ldap._tcp.{}'.format(domain), '+time=1', '+tries=3']
        dig = subprocess.check_output(cmd)
        if 'ANSWER SECTION' in dig:
            NSLog('Ldap server is reachable by dig')
            return True
        else:
            NSLog('Ldap server is not reachable by dig')
            return False
    except subprocess.CalledProcessError:
        NSLog('Ldap server is not reachable by dig')
        return False


def is_network_volume(share_path):
    '''NSWorkspace alows us to check for filesystem type of a specified path'''
    #pylint: disable=C0301,C0103
    ws = NSWorkspace.alloc().init()
    share_type = ws.getFileSystemInfoForPath_isRemovable_isWritable_isUnmountable_description_type_(share_path,
                                                                                                    None,
                                                                                                    None,
                                                                                                    None,
                                                                                                    None,
                                                                                                    None)[-1]
    return True if share_type == 'smbfs' or share_type == 'webdav' else False
    #pylint: enable=C0301,C0103


def get_mounted_network_volumes():
    '''Uses Foundation.NSFileManager to get mounted volumes. is_network_volume() is called
        to filter out volumes that are not of type "smbfs"'''
    #pylint: disable=C0103
    fm = NSFileManager.alloc().init()
    mounts = fm.mountedVolumeURLsIncludingResourceValuesForKeys_options_(None, 0)
    mount_paths = []
    for mount in mounts:
        mount_path = mount.fileSystemRepresentation()
        if is_network_volume(mount_path):
            mount_paths.append(mount_path)
    return mount_paths
    #pylint: enable=C0103

def mount_share(share_url, notifications=True):
    thread = CustomThread(url=share_url,
                          display_notifications=notifications)
    thread.daemon = True
    thread.start()


def unmount_share(mount_path, notifications):
    thread = CustomThread(unmount=mount_path,
                          display_notifications=notifications)
    thread.daemon = True
    thread.start()


def _unmount_share_cmd(mount_path):
    '''Unmounts share using hdiutil, would like to use something other than subprocess'''
    out = subprocess.check_output(['/usr/bin/hdiutil', 'unmount', mount_path])
    return out


def open_file(file_path):
    '''Opens file/folder at specified path'''
    file_url = NSURL.fileURLWithPath_(file_path)
    NSWorkspace.sharedWorkspace().openURL_(file_url)
    NSLog('User opened {0}'.format(file_path))


def notify(title, subject):
    '''Displays a notification if user has not disable ShareMounter in
       notification center'''
    notification = NSUserNotification.alloc().init()
    notification.setTitle_(title)
    notification.setInformativeText_(subject)
    notification.setSoundName_('NSUserNotificationDefaultSoundName')
    NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(notification)

def _get_console_user():
    return SCDynamicStoreCopyConsoleUser(None, None, None)[0]


class ConfigManager(object):

    def __init__(self):
        self.protocol_map = {
            'http': 'http',
            'https': 'htps',
            'smb': 'smb ',
            'afp': 'afp ',
            'cifs': 'cifs'
        }
        self.global_config = dict()
        self.managed_shares = list()
        self.user_added_shares = list()
        self.user_config = dict()
        self.domain = str()
        self.principal = str()
        self.load_prefs()

    def validate_kerberos(self):
        def _update_login():
            try:
                if not ad.bound() or not kerberos.check_keychain(self.principal):
                    d = PyDialog.PasswordDialog()
                    d.display()
                    self.principal = ad._format_principal(d.username())
                    self.domain = ad._split_principal(d.username())[1]
                    if ad.accessible(self.domain):
                        result = kerberos.test_kerberos_password(self.principal,
                                                                 d.password())
                        if result != True:
                            _update_login()
                else:
                    if ad.accessible(self.domain):
                        success = kerberos.test_kerberos_password(self.principal, _update_password())
                        if not success:
                            _update_login()
            except ad.PrincipalFormatError:
                message = 'Username must be formatted as user@domain.com'
                username_dialog = PyDialog.AlertDialog('Invalid username!',
                                                       message)
                username_dialog.display()
                self.validate_kerberos()

        def _update_password():
            message = 'Enter the password for {0}'.format(self.principal)
            d = PyDialog.SecureInputDialog('Could not find keychain entry!', message)
            d.display()
            return d.get_input()

        if not self.domain or not self.principal:
            _update_login()

        if not kerberos.check_keychain(self.principal):
            _update_login()

        kerberos.delete_expired_tickets()

        if kerberos.tickets() == []:
            NSLog('Could not find a valid Kerberos ticket. Requesting new ticket now...')
            success = kerberos.kinit_keychain_command(self.principal)
            result = ('New Kerberos ticket granted!' if success
                      else 'Unable to get new Kerberos ticket')
            if kerberos.tickets() == []:
                kerberos.refresh_ticket()
            NSLog(result)
        else:
            NSLog('Kerberos ticket exists in cache. Attempting to renew ticket...')
            success = kerberos.refresh_ticket()
            result = ('Successfully renewed Kerberos ticket!' if success
                      else 'Unable to renew Kerberos ticket!')
            NSLog(result)
        self.save_prefs()


    def _get_base_args(self, server_url, username):
        parsed_url = urlparse.urlparse(server_url)
        args = [
            '-l', parsed_url.netloc,
            '-a', username,
            '-s', parsed_url.netloc,
            '-p', parsed_url.path,
            '-r', self.protocol_map[parsed_url.scheme],
        ]
        return args


    def check_keychain(self, server_url, username, return_code=True):
        args = self._get_base_args(server_url, username)
        if keychain('find', 'internet', args):
            return True
        else:
            return False


    def add_share_to_keychain(self, server_url, username, password):
        args = self._get_base_args(server_url, username) + [
            '-w', password,
            '-T', '/usr/bin/security',
            '-T', '/System/Library/CoreServices/NetAuthAgent.app/Contents/MacOS/NetAuthSysAgent',
            '-T', '/System/Library/CoreServices/NetAuthAgent.app/',
            '-T', 'group://NetAuth',
            '-D', 'Network Password',
        ]
        output = keychain('add', 'internet', args)
        if output == None:
            NSLog('Failed to add keychain entry')
            return False
        else:
            NSLog('Successfully added keychain entry')
            return True


    def delete_share_from_keychain(self, server_url, username):
        args = self._get_base_args(server_url, username)
        if keychain('delete', 'internet', args):
            return True
        else:
            return False


    def save_prefs(self):
        self.write_pref('managed_shares', self.managed_shares)
        self.write_pref('user_added_shares', self.user_added_shares)
        self.write_pref('principal', self.principal)
        self.write_pref('domain', self.domain)
        # self.write_pref('display_notifications')
        # self.user_config['managed_shares'] = self.managed_shares
        # self.user_config['user_added_shares'] = self.user_added_shares
        # self.user_config['principal'] = self.principal
        # self.user_config['domain'] = self.domain
        # FoundationPlist.writePlist(self.user_config, user_preferences_path)


    def load_global_prefs(self):
        self.global_config = FoundationPlist.readPlist(global_preferences_path)
        # self.managed_shares = self.read_managed_pref('network_shares')

    def write_pref(self, key, value):
        CFPreferencesSetAppValue(key, value, kCFPreferencesCurrentApplication)
        if not CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication):
            d = PyDialog.AlertDialog('Something went wrong...',
                                     'Unable to save preference: "{0}"'.format(key))
            d.display()
            NSLog('ERROR: unable to save user preferences!')

    def read_managed_pref(self, pref_key):
        return CFPreferencesCopyAppValue(pref_key, kCFPreferencesCurrentApplication)


    def load_prefs(self):
        NSLog('Loading user preferences...')
        defaults = {
            'managed_shares': list(),
            'user_added_shares': list(),
            'display_notifications': True,
            'group_membership': list(),
        }
        # if not os.path.exists(user_preferences_path):
        #     self.user_config = defaults
        # else:
        #     self.user_config = FoundationPlist.readPlist(user_preferences_path)
        #     for key, value in defaults.iteritems():
        #         if key not in self.user_config.keys():
        #             self.user_config[key] = value
        if self.read_managed_pref('managed_shares'):
            self.managed_shares = [dict(share) for share in self.read_managed_pref('managed_shares')]
        else:
            self.managed_shares = list()

        if self.read_managed_pref('user_added_shares'):
            self.user_added_shares = [dict(share) for share in self.read_managed_pref('user_added_shares')]
        else:
            self.user_added_shares = list()

        if ad.bound():
            self.domain = ad.domain_dns()
            self.principal = ad.principal()
        else:
            self.domain = self.read_managed_pref('domain')
            self.principal = self.read_managed_pref('principal')

        self.save_prefs()


    def get_sharebykey(self, key, value):
        for network_share in self.managed_shares:
            if network_share[key] == value:
                return network_share
        for network_share in self.user_added_shares:
            if network_share[key] == value:
                return network_share


    def get_managedshare_bykey(self, key, value):
        for index, network_share in enumerate(self.managed_shares):
            if network_share[key] == value:
                return network_share, index
            else:
                continue
        return None, None


    def get_useradded_bykey(self, key, value):
        for index, network_share in enumerate(self.user_added_shares):
            if network_share[key] == value:
                return network_share, index
        return None, None


    def _process_networkshare(self, network_share, share_type='managed', hide=False, auto_connect=False, username=''):
        processed_share = {
            'mount_point': '/Volumes/{0}'.format(os.path.basename(network_share['share_url'])),
            'connect_automatically': auto_connect,
            'hide_from_menu': hide,
            'share_type': share_type,
            'title': network_share['title'],
            'share_url': network_share['share_url']
        }
        if network_share.get('groups'):
            processed_share['groups'] = network_share.get('groups')
        if share_type == 'user':
            processed_share['username'] = username
        return processed_share

    def get_mappedshares(self, membership):
        server_url = self.read_managed_pref('server_url')
        if server_url:
            NSLog('Requesting network shares from {0}'.format(server_url))
            try:
                r = requests.get(server_url, params={'membership': membership})
                mapped_shares = r.json()['managed_shares']
                NSLog('Successfully retrieved network shares from server.')
            except requests.exceptions.ConnectionError:
                return None
        else:
            NSLog('Attempting to load preferences from plist')
            mapped_shares = [network_share
                             for network_share in self.read_managed_pref('network_shares')
                             for group in membership
                             if group in network_share['groups']]
            NSLog('Loaded mapped shares!')
        return mapped_shares

    def update_managedshares(self, principal):
        NSLog('Updating managed shares...')
        membership = ad.membership(self.principal)
        mapped_shares = self.get_mappedshares(membership)
        mapped_share_titles = [share['title'] for share in mapped_shares]
        for mapped_share in mapped_shares:
            existing_share, index = self.get_managedshare_bykey('title', mapped_share['title'])
            if existing_share:
                NSLog('Updating existing share')
                if existing_share['share_url'] != mapped_share['share_url']:
                    self.managed_shares[index]['share_url'] = mapped_share['share_url']
                if existing_share['groups'] != mapped_share['groups']:
                    self.managed_shares[index]['groups'] = mapped_share['groups']
            else:
                NSLog('Processing new network share: {0}'.format(mapped_share.get('title')))
                processed_share = self._process_networkshare(mapped_share)
                self.managed_shares.append(processed_share)

        if self.read_managed_pref('include_smb_home'):
            NSLog('Getting SMB Home info...')
            existing, index = self.get_managedshare_bykey('share_type', 'smb_home')
            if ad.bound():
                smbhome = ad.smbhome()
                username = ad._get_consoleuser()
                if existing:
                    NSLog('SMB Home already exists in config. Updating...')
                    if existing.get('title') != username:
                        self.managed_shares[index]['share_title'] = username
                    if existing.get('share_url') != smbhome:
                        self.managed_shares[index]['share_url'] = smbhome
                else:
                    network_share = {'title': username, 'share_url': smbhome}
                    processed = self._process_networkshare(network_share,
                                                          share_type='smb_home')
                    self.managed_shares.append(processed)
                NSLog('Done checking for SMB Info...')
            else:
                NSLog('Computer is not bound. Skipping SMB Home...')

        current_shares = list(self.managed_shares)
        for network_share in current_shares:
            if (network_share.get('title') not in mapped_share_titles
                and network_share.get('share_type') != 'smb_home'):
                self.managed_shares.remove(network_share)

        self.save_prefs()
        NSLog('Managed shares have been updated!')


    def _process_membership(self, group_membership):
        print group_membership
        print self.read_managed_pref('network_shares')
        mapped_shares = [network_share
                         for network_share in self.read_managed_pref('network_shares')
                         for group in group_membership
                         if group in network_share['groups']]
        return mapped_shares


    def add_or_update_usershare(self, title, url, hide, auto_connect, username=''):
        network_share = {'title': title, 'share_url': url}
        existing_share, index = self.get_useradded_bykey('title', title)
        processed_share = self._process_networkshare(network_share, hide=hide,
                                                    auto_connect=auto_connect,
                                                    share_type='user_added',
                                                    username=username)
        if existing_share:
            self.user_added_shares[index] = processed_share
        else:
            self.user_added_shares.append(processed_share)
        self.save_prefs()


# borrowed from Imagr and modified for this app
class CustomThread(threading.Thread):
    '''Class for running a process in its own thread'''

    def __init__(self, url=None, unmount=None, mountpoint=None, display_notifications=True):
        threading.Thread.__init__(self)
        if url:
            self.url = url.replace(' ', '%20')
        else:
            self.url = url
        self.unmount = unmount
        self.display_notifications = display_notifications

    def run(self):
        try:
            if self.url:
                NSLog('Attempting to mount {0}'.format(self.url))
                mount_location = mount_shares_better.mount_share(self.url, show_ui=True)
                message = 'Successfully mounted {0}'.format(self.url)
                NSLog(message)
                if self.display_notifications:
                    notify(message, mount_location)
            elif self.unmount:
                NSLog('Attempting to unmount {0}'.format(self.unmount))
                _unmount_share_cmd(self.unmount)
                message = 'Successfully unmounted {0}'.format(self.unmount)
                NSLog(message)
                if self.display_notifications:
                    notify('Network share no longer available', message)
        except Exception as e:

            if self.url:
                message = 'There was a problem mounting share {0}'.format(self.url.replace('%20', ' '))
                alert = PyDialog.AlertDialog('Could not mount share!', message)
                alert.display()
                NSLog(message)
            if self.unmount:
                message = 'There was a problem unmounting {0}'.format(self.unmount)
                alert = PyDialog.AlertDialog('Something went wrong!', message)
                alert.display()
                NSLog(message)
            pass
