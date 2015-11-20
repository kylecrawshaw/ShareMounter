import nose
import mock
from pymacad import ad
import unittest
import subprocess



class TestBound(unittest.TestCase):
    _dsconfigad_bound = """
Active Directory Forest          = test.com
Active Directory Domain          = test.com
Computer Account                 = test-machine$

Advanced Options - User Experience
Create mobile account at login = Disabled
Require confirmation        = Disabled
Force home to startup disk     = Enabled
Mount home as sharepoint    = Enabled
Use Windows UNC path for home  = Enabled
Network protocol to be used = smb
Default user Shell             = /bin/bash

Advanced Options - Mappings
Mapping UID to attribute       = not set
Mapping user GID to attribute  = not set
Mapping group GID to attribute = not set
Generate Kerberos authority    = Enabled

Advanced Options - Administrative
Preferred Domain controller    = not set
Allowed admin groups           = TEST\STAFF
Authentication from any domain = Enabled
Packet signing                 = allow
Packet encryption              = allow
Password change interval       = 14
Restrict Dynamic DNS updates   = not set
Namespace mode                 = domain
"""
    _dsconfigad_notbound = ""
    _side_effect=subprocess.CalledProcessError(1, ['dsconfigad', '-show'], output="")

    @mock.patch('pymacad.ad._cmd_dsconfigad_show', mock.Mock(return_value=_dsconfigad_notbound))
    def test_bound_false(self):
        self.assertFalse(ad.bound())

    @mock.patch('pymacad.ad._cmd_dsconfigad_show', mock.Mock(return_value=_dsconfigad_bound))
    def test_bound_true(self):
        nose.tools.ok_(ad.bound())

    @mock.patch('pymacad.ad._cmd_dsconfigad_show', mock.Mock(side_effect=_side_effect))
    def test_bound_exception(self):
        nose.tools.assert_raises(subprocess.CalledProcessError, ad.bound)


class TestPrincipal(unittest.TestCase):

    _dscl_search_notreachable= """
AuthenticationAuthority: ;ShadowHash;HASHLIST:<SALTED-SHA512-PBKDF2> ;Kerberosv5;;testuser@LKDC:SHA1.8392019230AABB3399494BB1191999AAAF999AA;LKDC:SHA1.8392019230AABB3399494BB1191999AAAF999AA ;Kerberosv5Cert;;9170197410974109731097BBAA10101001029CC@LKDC:SHA1.9170197410974109731097BBAA10101001029CC;LKDC:SHA1.9170197410974109731097BBAA10101001029CC;
"""

    _dscl_search_reachable = _dscl_search_notreachable +  """
AuthenticationAuthority: ;Kerberosv5;;testuser@TEST.COM;TEST.COM; ;NetLogon;testuser;TEST
No such key: AuthenticationAuthority
"""

    @mock.patch('pymacad.ad.bound', mock.Mock(return_value=False))
    def test_principal_notbound(self):
        nose.tools.assert_raises(ad.NotBound, ad.principal)

    @mock.patch('pymacad.ad.bound', mock.Mock(return_value=True))
    @mock.patch('pymacad.ad._cmd_dscl_search', mock.Mock(return_value=_dscl_search_reachable))
    def test_principal_ok(self):
        nose.tools.eq_("testuser@TEST.COM", ad.principal('testuser'))

    @mock.patch('pymacad.ad.bound', mock.Mock(return_value=True))
    @mock.patch('pymacad.ad._cmd_dscl_search', mock.Mock(return_value=_dscl_search_reachable))
    @mock.patch('pymacad.ad._extract_principal', mock.Mock(side_effect=AttributeError))
    def test_principal_attribute_error(self):
        nose.tools.assert_raises(ad.NotReachable, ad.principal)

    _side_effect=subprocess.CalledProcessError(1, ['dscl', '/Search', 'read', 'testuser', 'AuthenticationAuthority'], output="")
    @mock.patch('pymacad.ad.bound', mock.Mock(return_value=True))
    @mock.patch('pymacad.ad._cmd_dscl_search', mock.Mock(return_value=_dscl_search_reachable))
    @mock.patch('pymacad.ad._extract_principal', mock.Mock(side_effect=_side_effect))
    def test_principal_process_error(self):
        nose.tools.assert_raises(subprocess.CalledProcessError, ad.principal)

class TestDig(unittest.TestCase):
    _dig_ok = """
;; Truncated, retrying in TCP mode.

; <<>> DiG 9.8.3-P1 <<>> -t srv _ldap._tcp.test.com
;; global options: +cmd
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 616
;; flags: qr aa rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 2, ADDITIONAL: 2

;; QUESTION SECTION:
;_ldap._tcp.test.com.   IN      SRV

;; ANSWER SECTION:
_ldap._tcp.test.com.    600 IN  SRV     0 100 389 ad.test.com.

;; AUTHORITY SECTION:
test.com.       1800    IN      NS      ns1.test.com.
test.com.       1800    IN      NS      ns2.test.com.

;; ADDITIONAL SECTION:
ns1.test.com. 1200      IN A    10.0.0.1
ns2.test.com. 1200      IN A    10.0.0.2

;; Query time: 1 msec
;; SERVER: 10.0.0.2#53(10.0.0.2)
;; WHEN: Mon Oct 17 11:20:54 2015
"""

    _dig_notok = """
; <<>> DiG 9.8.3-P1 <<>> -t srv _ldap._tcp.test.com
;; global options: +cmd
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 696
;; flags: qr aa rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 1, ADDITIONAL: 0

;; QUESTION SECTION:
;_ldap._tcp.test.com.   IN      SRV

;; AUTHORITY SECTION:
        .                       10800   IN      SOA     a.root-servers.net. nstld.verisign-grs.com. 2015101900 1800 900 604800 86400

;; Query time: 21 msec
;; SERVER: 10.0.0.2#53(10.0.0.2)
;; WHEN: Mon Oct 17 11:20:54 2015
"""

    @mock.patch('pymacad.ad._cmd_dig_check', mock.Mock(return_value=_dig_ok))
    def test_accessible_ok(self):
        nose.tools.ok_(ad.accessible('TEST.COM'))

    @mock.patch('pymacad.ad._cmd_dig_check', mock.Mock(return_value=_dig_notok))
    def test_accessible_ok(self):
        self.assertFalse(ad.accessible('TEST.COM'))

    _side_effect=subprocess.CalledProcessError(1, ['dig', '-t', 'srv', '_ldap._tcp.TEST.COM'], output="")
    @mock.patch('pymacad.ad._cmd_dig_check', mock.Mock(side_effect=_side_effect))
    def test_accessible_processerror(self):
        nose.tools.assert_raises(subprocess.CalledProcessError, ad.accessible, 'TEST.COM')
