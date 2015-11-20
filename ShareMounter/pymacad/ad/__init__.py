import subprocess
import SystemConfiguration

def _get_consoleuser():
    return SystemConfiguration.SCDynamicStoreCopyConsoleUser(None, None, None)[0]


def _cmd_dig_check(domain):
    try:
        dig = subprocess.check_output(['dig', '-t', 'srv', '_ldap._tcp.' + domain])
    except subprocess.CalledProcessError:
        raise
    else:
        return dig


def _cmd_dsconfigad_show():
    return subprocess.check_output(['dsconfigad', '-show'])


def _cmd_dscl(nodename='.', scope=None, query=None, user=_get_consoleuser(), plist=False):
    if not scope:
        scope = '/Users/{0}'.format(user)
    cmd = ['/usr/bin/dscl', nodename, '-read', scope]
    if plist:
        cmd.insert(1, '-plist')
    if query:
        cmd.append(query)
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        if plist:
            import plistlib
            return plistlib.readPlistFromString(output)
        else:
            return output
    except subprocess.CalledProcessError:
        return None


def _cmd_ldapsearch(domain, fields=None):
    ldap_url = 'ldap://{0}'.format(domain)
    domain_split = domain.split('.')
    base = 'dc={0},dc={1}'.format(domain_split[0],domain_split[1])
    cmd = ['ldapsearch', '-LLL', '-Q', '-H', ldap_url, '-b', base]
    if fields:
        if isinstance(fields, list):
            cmd.extend(fields)
        else:
            cmd.append(fields)
    if not accessible(domain):
        raise NotReachable
    out = subprocess.check_output(cmd)
    return out


def bound():
    try:
        output = _cmd_dsconfigad_show()

        if "Active Directory" in output:
            return True
        else:
            return False
    except subprocess.CalledProcessError:
        raise


def searchnodes():
    if not bound():
        raise NotBound
    net_config = SystemConfiguration.SCDynamicStoreCreate(None, 'directory-nodes', None, None)
    nodes = SystemConfiguration.SCDynamicStoreCopyValue(net_config, 'com.apple.opendirectoryd.node:/Search')
    if nodes:
        return list(nodes)
    else:
        return None


def adnode():
    if not bound():
        raise NotBound
    nodes = searchnodes()
    ad_node = [node for node in nodes if 'Active Directory' in node]
    return ad_node[0] if ad_node else None


def domain_dns():
    if not bound():
        raise NotBound
    net_config = SystemConfiguration.SCDynamicStoreCreate(None, 'active-directory', None, None)
    ad_info = SystemConfiguration.SCDynamicStoreCopyValue(net_config, 'com.apple.opendirectoryd.ActiveDirectory')
    if ad_info:
        return ad_info.get('DomainNameDns')
    else:
        return None


class ProcessError(subprocess.CalledProcessError):
    pass


class NotReachable(Exception):
    '''Domain is unreachable'''
    pass


class NotBound(Exception):
    '''Computer is not bound to a Directory Service'''
    pass


class PrincipalFormatError(Exception):
    '''Principal is formatted incorrectly. Must be "someuser@DOMAIN.COM"
       or "someuser@domain.com"'''
    pass

def _extract_principal(string):
    import re
    try:
        match = re.search(r'[a-zA-Z0-9+_\-\.]+@[^;]+\.[A-Z]{2,}', string, re.IGNORECASE)
        match = match.group()
    except AttributeError:
        raise
    else:
        return match


def _format_principal(principal):
    try:
        p_split = _split_principal(principal)
        formatted = '{0}@{1}'.format(p_split[0], p_split[1].upper())
    except IndexError:
        raise PrincipalFormatError('Invalid format for principal!')
    return formatted

def _split_principal(principal):
    '''Returns user and domain tuple'''
    p_split = principal.split('@')
    if len(p_split) == 2:
        return p_split
    else:
        raise PrincipalFormatError('Invalid format for principal: {0}'.format(principal))


def principal(user=_get_consoleuser()):
    """Returns the principal of the current user when computer is bound"""

    if not bound():
        raise NotBound

    user_path = '/Users/' + user

    try:
        output = _cmd_dscl('/Search', query='AuthenticationAuthority', scope=user_path)
        if not output:
            return None
        result = _extract_principal(output)
        return result
    except AttributeError:
        raise NotReachable
    except subprocess.CalledProcessError:
        raise
    else:
        return None


def accessible(domain=''):
    if domain == '':
        domain = domain_dns()
    try:
        dig = _cmd_dig_check(domain)
    except subprocess.CalledProcessError:
        raise
    else:
        if 'ANSWER SECTION' not in dig:
            return False
        else:
            return True


def membership(principal):
    user, domain = _split_principal(principal)
    fields = ['sAMAccountName={0}'.format(user), 'memberOf']
    ldap_query = _cmd_ldapsearch(domain, fields=fields)
    if ldap_query:
        membership = [line[line.find('CN=')+3:line.find(',')]
                      for line in ldap_query.split('\n')
                      if 'memberOf' in line]
        return membership
    else:
        return None


def realms():
    if not bound():
        raise NotBound
    store = SystemConfiguration.SCDynamicStoreCreate(None, 'default-realms', None, None)
    realms = SystemConfiguration.SCDynamicStoreCopyValue(store, 'Kerberos-Default-Realms')
    return list(realms) if realms else None


def smbhome(node='.', user=_get_consoleuser()):
    if not bound():
        raise NotBound
    output = _cmd_dscl(nodename=node, query='SMBHome', user=user)
    if output and 'No such key:' not in output:
        out_split = output.split(' ')[1]
        smb_home = out_split.replace('\\\\', '/').replace('\\', '/').strip('\n')
        smb_url = '{0}{1}'.format('smb:/', smb_home)
        return smb_url
    else:
        return ''
