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
        # cmd = ['dig', '-t', 'srv', '_ldap._tcp.{}'.format(domain), '+time=1', '+tries=3']
        # dig = subprocess.check_output(cmd)
        # if 'ANSWER SECTION' in dig:
        if ad.accessible(domain):
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

def mount_share(share_url):
    thread = CustomThread(url=share_url)
    thread.daemon = True
    thread.start()


def unmount_share(mount_path):
    thread = CustomThread(unmount=mount_path)
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
    if read_pref('display_notifications'):
        notification = NSUserNotification.alloc().init()
        notification.setTitle_(title)
        notification.setInformativeText_(subject)
        notification.setSoundName_('NSUserNotificationDefaultSoundName')
        NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(notification)


def _get_console_user():
    return SCDynamicStoreCopyConsoleUser(None, None, None)[0]


def write_pref(key, value):
    # NSLog('Setting "{0}" to "{1}"'.format(key, value))
    CFPreferencesSetAppValue(key, value, kCFPreferencesCurrentApplication)
    if not CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication):
        d = PyDialog.AlertDialog('Something went wrong...',
                                 'Unable to save preference: "{0}"'.format(key))
        d.display()
        NSLog('ERROR: unable to save user preferences!')

def read_pref(pref_key):
    return CFPreferencesCopyAppValue(pref_key, kCFPreferencesCurrentApplication)


def get_managed_shares():
    managed_shares = list(read_pref('managed_shares'))
    return [dict(share) for share in managed_shares]

def get_user_added_shares():
    user_added_shares = list(read_pref('user_added_shares'))
    return [dict(share) for share in user_added_shares]


class ConfigManager(object):

    def __init__(self):
        self.load_prefs()

    def validate_kerberos(self):
        NSLog('Checking and updating Kerberos if necessary...')
        def _update_login():
            try:
                if not ad.bound():
                    d = PyDialog.PasswordDialog()
                    selection = d.display()
                    if selection:
                        principal = ad._format_principal(d.username())
                        domain = ad._split_principal(d.username())[1]
                        write_pref('principal', principal)
                        write_pref('domain', domain)
                        if is_ldap_reachable(read_pref('domain')):
                            result = kerberos.test_kerberos_password(read_pref('principal'),
                                                                     d.password())
                            if result != True:
                                _update_login()
                else:
                    if is_ldap_reachable(read_pref('domain')):
                        success = kerberos.test_kerberos_password(read_pref('principal'), _update_password())
                        if not success:
                            _update_login()
            except ad.PrincipalFormatError:
                message = 'Username must be formatted as user@domain.com'
                username_dialog = PyDialog.AlertDialog('Invalid username!',
                                                       message)
                username_dialog.display()
                self.validate_kerberos()

        def _update_password():
            message = 'Enter the password for {0}'.format(read_pref('principal'))
            d = PyDialog.SecureInputDialog('Could not find keychain entry!', message)
            d.display()
            return d.get_input()


        if not read_pref('domain') or not read_pref('principal'):
            _update_login()


        if is_ldap_reachable(read_pref('domain')):
            if not kerberos.check_keychain(read_pref('principal')):
                _update_login()
            if kerberos.tickets() == []:
                NSLog('Could not find a valid Kerberos ticket. Requesting new ticket now...')
                success = kerberos.kinit_keychain_command(read_pref('principal'))
                result = ('New Kerberos ticket granted!' if success
                          else 'Unable to get new Kerberos ticket')
                notify(result, '')
                NSLog(result)
            else:
                NSLog('Kerberos ticket exists in cache. Attempting to renew ticket...')
                if not kerberos.refresh_ticket():
                    success = kerberos.kinit_keychain_command(read_pref('principal'))
                else:
                    success = True
                result = ('Successfully renewed Kerberos ticket!' if success
                          else 'Unable to renew Kerberos ticket!')
                notify(result, '')
                NSLog(result)
            kerberos.delete_expired_tickets()


    def _get_base_args(self, server_url, username):
        protocol_map = {
            'http': 'http',
            'https': 'htps',
            'smb': 'smb ',
            'afp': 'afp ',
            'cifs': 'cifs'
        }
        parsed_url = urlparse.urlparse(server_url)
        args = [
            '-l', parsed_url.netloc,
            '-a', username,
            '-s', parsed_url.netloc,
            '-p', parsed_url.path,
            '-r', protocol_map[parsed_url.scheme],
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


    def load_prefs(self):
        NSLog('Loading user preferences...')
        defaults = {
            'managed_shares': list(),
            'user_added_shares': list(),
            'display_notifications': True,
            'group_membership': list(),
            'domain': '',
            'principal': ''
        }
        for key, value in defaults.iteritems():
            if not read_pref(key):
                write_pref(key, value)
        if ad.bound():
            write_pref('domain', ad.domain_dns())
            write_pref('principal', ad.principal())


    def get_sharebykey(self, key, value):
        managed_shares = get_managed_shares()
        user_added_shares = get_user_added_shares()
        for network_share in managed_shares:
            if network_share[key] == value:
                return network_share
        for network_share in user_added_shares:
            if network_share[key] == value:
                return network_share


    def get_managedshare_bykey(self, key, value):
        managed_shares = get_managed_shares()
        for index, network_share in enumerate(managed_shares):
            if network_share[key] == value:
                return network_share, index
            else:
                continue
        return None, None


    def remove_share(self, network_share):
        current_share = self.get_share_bykey('title', network_share.get('title'))
        user_added_shares = get_user_added_shares()
        managed_shares = get_managed_shares()
        if current_share:
            if current_share.get('share_type') == 'managed':
                managed_shares.remove(current_share)
                write_pref('managed_shares', managed_shares)
            else:
                user_added_shares.remove(user_share)
                write_pref('user_added_shares', user_added_shares)


    def get_useradded_bykey(self, key, value):
        user_added_shares = get_user_added_shares()
        for index, network_share in enumerate(user_added_shares):
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
        server_url = read_pref('server_url')
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
            if read_pref('network_shares'):
                mapped_shares = [network_share
                                 for network_share in read_pref('network_shares')
                                 for group in membership
                                 if group in network_share['groups']]
            else:
                mapped_shares = list()
            NSLog('Loaded mapped shares!')
        return mapped_shares


    def update_managedshares(self):
        NSLog('Updating managed shares...')
        membership = ad.membership(read_pref('principal'))
        managed_shares = get_managed_shares()
        mapped_shares = self.get_mappedshares(membership)
        mapped_share_titles = [share['title'] for share in mapped_shares]
        for mapped_share in mapped_shares:
            existing_share, index = self.get_managedshare_bykey('title', mapped_share['title'])
            if existing_share:
                NSLog('Updating existing share')
                if existing_share['share_url'] != mapped_share['share_url']:
                    managed_shares[index]['share_url'] = mapped_share['share_url']
                if existing_share['groups'] != mapped_share['groups']:
                    managed_shares[index]['groups'] = mapped_share['groups']
            else:
                NSLog('Processing new network share: {0}'.format(mapped_share.get('title')))
                processed_share = self._process_networkshare(mapped_share)
                managed_shares.append(processed_share)
            write_pref('managed_shares', managed_shares)

        if read_pref('include_smb_home'):
            NSLog('Getting SMB Home info...')
            existing, index = self.get_managedshare_bykey('share_type', 'smb_home')
            if ad.bound():
                smbhome = ad.smbhome()
                username = ad._get_consoleuser()
                if existing:
                    NSLog('SMB Home already exists in config. Updating...')
                    if existing.get('title') != username:
                        managed_shares[index]['share_title'] = username
                    if existing.get('share_url') != smbhome:
                        managed_shares[index]['share_url'] = smbhome
                else:
                    network_share = {'title': username, 'share_url': smbhome}
                    processed = self._process_networkshare(network_share,
                                                          share_type='smb_home')
                    managed_shares.append(processed)
                NSLog('Done checking for SMB Info...')
            else:
                NSLog('Computer is not bound. Skipping SMB Home...')
            write_pref('managed_shares', managed_shares)

        current_shares = list(managed_shares)
        for network_share in current_shares:
            if (network_share.get('title') not in mapped_share_titles
                and network_share.get('share_type') != 'smb_home'):
                remove_share(network_share)
        NSLog('Managed shares have been updated!')


    def _process_membership(self, group_membership):
        mapped_shares = [network_share
                         for network_share in read_pref('network_shares')
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
        user_added_shares = get_user_added_shares()
        if existing_share:
            user_added_shares[index] = processed_share
        else:
            user_added_shares.append(processed_share)
        write_pref('user_added_shares', user_added_shares)


    def add_or_update_managedshare(self, title, url, hide, auto_connect, username=''):
        network_share = {'title': title, 'share_url': url}
        existing_share, index = self.get_managedshare_bykey('title', title)
        processed_share = self._process_networkshare(network_share, hide=hide,
                                                    auto_connect=auto_connect,
                                                    share_type='managed')
        managed_shares = get_managed_shares()
        if existing_share:
            managed_shares[index] = processed_share
        else:
            managed_shares.append(processed_share)
        write_pref('user_added_shares', user_added_shares)


    def update_share(self, modified_share, index):
        if modified_share.get('share_type') in ['managed', 'smb_home']:
            managed_shares = get_managed_shares()
            managed_shares[index] = modified_share
            write_pref('managed_shares', managed_shares)
        if modified_share.get('share_type') == 'user_added_share':
            user_added_shares = get_user_added_shares()
            user_added_shares[index] = modified_share
            write_pref('user_added_shares', user_added_shares)


# borrowed from Imagr and modified for this app
class CustomThread(threading.Thread):
    '''Class for running a process in its own thread'''

    def __init__(self, url=None, unmount=None, mountpoint=None):
        threading.Thread.__init__(self)
        if url:
            self.url = url.replace(' ', '%20')
        else:
            self.url = url
        self.unmount = unmount


    def run(self):
        try:
            if self.url:
                NSLog('Attempting to mount {0}'.format(self.url))
                mount_location = mount_shares_better.mount_share(self.url, show_ui=True)
                message = 'Successfully mounted {0}'.format(self.url)
                NSLog(message)
                notify(message, mount_location)
            elif self.unmount:
                NSLog('Attempting to unmount {0}'.format(self.unmount))
                _unmount_share_cmd(self.unmount)
                message = 'Successfully unmounted {0}'.format(self.unmount)
                NSLog(message)
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
