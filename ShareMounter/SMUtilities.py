#pylint: disable=E0611
from SystemConfiguration import SCDynamicStoreCreate, \
                                SCDynamicStoreCopyValue, \
                                SCDynamicStoreCopyConsoleUser
from Foundation import NSFileManager, NSLog
from AppKit import NSWorkspace, NSUserNotificationCenter, NSUserNotification, \
                   NSURL
import FoundationPlist
import os, subprocess, plistlib, urlparse
import mount_shares_better
import threading
import PyDialog

homedir = os.path.expanduser('~')
user_preferences_path = os.path.join(homedir, 'Library/Preferences/ShareMounter.plist')
global_preferences_path = '/Library/Preferences/ShareMounter.plist'


def keychain(action_type, item_type, args, return_code=False):
    if item_type not in ['generic', 'internet']:
        raise Exception()
    if action_type not in ['add', 'find', 'delete']:
        raise Exception()
    action = '{0}-{1}-password'.format(action_type, item_type)
    user_keychain = os.path.expanduser('~/Library/Keychains/login.keychain')
    cmd = ['/usr/bin/security', action] + args + [user_keychain]
    if return_code:
        return subprocess.call(cmd)
    else:
        try:
            out = subprocess.check_output(cmd)
            return out
        except subprocess.CalledProcessError as e:
            return None


def dscl(username, query=None, nodename='.'):
    scope = '/users/{0}'.format(username)
    cmd = ['dscl', '-plist', nodename, '-read', scope]
    if query:
        cmd.append(query)
    try:
        output = subprocess.check_output(cmd)
        data = FoundationPlist.readPlistFromString(output)
        return data
    except subprocess.CalledProcessError:
        return None


def is_ldap_reachable(domain):
    '''Checks whether or not the ldap server can be reached. Returns True.'''
    try:
        cmd = ['dig', '-t', 'srv', '_ldap._tcp.{}'.format(domain), '+time=1', '+tries=1']
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
    '''Uses NSFileManager to get mounted volumes. is_network_volume() is called
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


class DirectoryUser(object):


    def __init__(self):
        self.console_user = _get_console_user()
        self.ad_local_info = dscl(self.console_user)


    def get_aduserinfo(self):
        return dscl(self.console_user, nodename=self.get_nodename())


    def get_nodename(self):
        return self.ad_local_info['dsAttrTypeStandard:OriginalNodeName'][0]


    def get_membership(self):
        ad_user = self.get_aduserinfo()
        if ad_user:
            groups_raw = ad_user['dsAttrTypeNative:memberOf']
            groups = [group[group.find('CN=')+3:group.find(',')] for group in groups_raw]
            return groups
        else:
            return list()


    def get_smb_home_url(self):
        smb_home_raw = self.ad_local_info['dsAttrTypeNative:original_smb_home'][0]
        smb_home = smb_home_raw.replace('\\\\', '/').replace('\\', '/')
        smb_url = '{0}{1}'.format('smb:/', smb_home)
        return smb_url


    def get_addomain(self):
        net_config = SCDynamicStoreCreate(None, 'active-directory', None, None)
        ad_info = SCDynamicStoreCopyValue(net_config, 'com.apple.opendirectoryd.ActiveDirectory')
        return ad_info.get('DomainNameDns')


class Kerberos(object):


    def __init__(self, directory_user):
        self.username = directory_user.console_user
        self.directory_info = directory_user.ad_local_info
        self.realm = self.get_kerbrealm()
        self.principal = '{0}@{1}'.format(self.username, self.realm)


    def get_kerbrealm(self):
        return self.get_kerbuser().split('@')[1].upper()


    def get_kerbuser(self):
        raw = self.directory_info['dsAttrTypeStandard:AltSecurityIdentities'][0]
        return raw.split(':')[1]


    def check_keychain(self):
        security_args = [
            '-a', self.username,
            '-l', self.realm + ' (' + self.username + ')',
            '-s', self.realm,
            '-c', 'aapl'
        ]
        return True if keychain('find', 'generic', security_args) else False


    def pass_to_keychain(self, username, password):
        """Saves password to keychain for use by kinit."""
        security_args = [
            '-a', username,
            '-l', self.realm,
            '-s', self.realm,
            '-c', 'aapl',
            '-T', '/usr/bin/kinit',
            '-w', str(password)
        ]
        return keychain('add', 'generic', security_args)


    def refresh_ticket(self):
        return_code = subprocess.call(['/usr/bin/kinit', '--renew'])
        if return_code == 0:
            return True
        else:
            return False


    def kinit_keychain_command(self):
        """Runs the kinit command with keychain password."""
        try:
            subprocess.check_output(['/usr/bin/kinit', '-l', '10h', '--renewable',
                                     self.principal])
            return True
        except:
            """exception most likely means a password mismatch,
            so we should run renewTicket again."""
            return False


    def test_kinit_password(self, password):
        """Runs the kinit command with supplied password."""
        renew1 = subprocess.Popen(['echo',password], stdout=subprocess.PIPE)
        renew2 = subprocess.Popen(['kinit','-l','10h','--renewable',
                                   '--password-file=STDIN','--keychain',
                                   self.principal],
                                   stderr=subprocess.PIPE,
                                   stdin=renew1.stdout,
                                   stdout=subprocess.PIPE)
        renew1.stdout.close()

        out = renew2.communicate()[1]
        if 'incorrect' in out:
            return False
        elif '':
            return True
        else:
            return out


    def kerberos_valid(self):
        '''Checks validity of kerberos ticket. Will attempt refresh if necessary.
           If unable to refresh, function will return false.'''
        if not self.check_keychain():
            self.prompt_for_password()
        response = subprocess.call(['klist', '--test'])
        if response == 0 and self.refresh_ticket():
            NSLog('Kerberos is valid and refreshed')
            return True
        else:
            if self.check_keychain():
                if self.kinit_keychain_command():
                    NSLog('Successfully renewed ticket from Keychain')
                    return True
            return False

    def prompt_for_password(self):
        NSLog('Need to add password to keychain')
        username = _get_console_user()
        message = 'Please enter the password for {0}'.format(username)
        d = PyDialog.SecureInputDialog('Session has expired!', message)
        d.display()
        self.pass_to_keychain(username, d.get_input())


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
        self.load_prefs()


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
        self.user_config['managed_shares'] = self.managed_shares
        self.user_config['user_added_shares'] = self.user_added_shares
        FoundationPlist.writePlist(self.user_config, user_preferences_path)


    def load_global_prefs(self):
        self.global_config = FoundationPlist.readPlist(global_preferences_path)


    def load_prefs(self):
        defaults = {
            'managed_shares': list(),
            'user_added_shares': list(),
            'display_notifications': True,
            'group_membership': list(),
        }
        self.load_global_prefs()
        if not os.path.exists(user_preferences_path):
            self.user_config = defaults
        else:
            self.user_config = FoundationPlist.readPlist(user_preferences_path)
            for key, value in defaults.iteritems():
                if key not in self.user_config.keys():
                    self.user_config[key] = value
        self.managed_shares = self.user_config.get('managed_shares')
        self.user_added_shares = self.user_config.get('user_added_shares')
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


    @staticmethod
    def _process_networkshare(network_share, share_type='managed', hide=False, auto_connect=False, username=''):
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


    def update_managedshares(self, directory_user):
        self.load_global_prefs()
        if self.global_config:
            NSLog('Updating managed shares...')
            mapped_shares = self._get_mappedshares(directory_user.get_membership())
            mapped_share_titles = [share['title'] for share in mapped_shares]
            for mapped_share in mapped_shares:
                existing_share, index = self.get_managedshare_bykey('title', mapped_share['title'])
                if existing_share:
                    if existing_share['share_url'] != mapped_share['share_url']:
                        self.managed_shares[index]['share_url'] = mapped_share['share_url']
                    if existing_share['groups'] != mapped_share['groups']:
                        self.managed_shares[index]['groups'] = mapped_share['groups']
                else:
                    processed_share = self._process_networkshare(mapped_share)
                    self.managed_shares.append(processed_share)

            if self.global_config.get('include_smb_home'):
                NSLog('Checking for SMB Home info...')
                existing, index = self.get_managedshare_bykey('share_type', 'smb_home')
                smbhome = directory_user.get_smb_home_url()
                username = directory_user.console_user
                if existing:
                    NSLog('SMB Home already exists in config. Updating if necessary...')
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
            current_shares = list(self.managed_shares)
            for network_share in current_shares:
                if (network_share.get('title') not in mapped_share_titles
                    and network_share.get('share_type') != 'smb_home'):
                    self.managed_shares.remove(network_share)

            self.save_prefs()
            NSLog('Managed shares have been updated!')


    def _get_mappedshares(self, group_membership):
        mapped_shares = [network_share
                         for network_share in self.global_config['network_shares']
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
                # if self.display_notifications:
                #     notify('There was a problem mounting share', self.url.replace('%20', ' '))
                NSLog(message)
            if self.unmount:
                message = 'There was a problem unmounting {0}'.format(self.unmount)
                alert = PyDialog.AlertDialog('Something went wrong!', message)
                alert.display()

                # if self.display_notifications:
                #     notify(message, '')
                NSLog(message)
            pass
