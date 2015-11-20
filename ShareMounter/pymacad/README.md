[![Build Status](https://travis-ci.org/Shufflepuck/pymacad.svg?branch=master)](https://travis-ci.org/Shufflepuck/pymacad)
[![codecov.io](https://codecov.io/github/Shufflepuck/pymacad/coverage.svg?branch=master)](https://codecov.io/github/ftiff/pymacad?branch=master)

# pymacad

## Acknowledgments

This python package is based on KerbMinder (http://github.com/pmbuko/KerbMinder).

* [Peter Bukowinski](http://github.com/pmbuko), author of KerbMinder
* [Francois 'ftiff' Levaux-Tiffreau](http://github.com/ftiff), who extracted this package
* [Ben Toms](http://github.com/macmule), who gave ftiff the idea
* [Allister Banks](https://twitter.com/Sacrilicious/status/543451138239258624) for pointing out an effective dig command to test for domain reachability.
* [Kyle Crawshaw](http://github.com/kcrawshaw), who extended it significantly

## pymacad.ad

I would suggest to use `from pymacad import ad` -- then call using ad.xxx

### Example
```python
>>> from pymacad import ad
>>> ad.bound()
False
>>> ad.accessible('TEST.COM')
False
>>> ad.accessible('FTI.IO')
True
```

### Functions

#### ad.bound()
checks if computer is bound to AD
- returns True or False
- raises subprocess.CalledProcessError

#### ad.principal(user)
gets principal from AD. If no user is specified, uses the current user.
- Returns principal
- Raises NotBound, NotReachable or subprocess.CalledProcessError

#### ad.accessible(domain)
checks if domain can be joined.
- Returns True or False
- raises subprocess.CalledProcessError

#### ad.searchnodes()
returns a list of available directories

#### ad.adnode()
returns the first Active Directory node or None

#### ad.get_domain_dns()
returns the DNS of domain, or raises NotBound

#### ad.membership(user)
Returns a list of groups belonging to this user
Raises NotBound

#### ad.realms()
Returns a list of Kerberos realms, or NotBound

#### ad.smb_home()
Returns the home URL of the user, or an empty string.

### Exceptions
- pymacad.ad.NotReachable
- pymacad.ad.NotBound
- subprocess.CalledProcessError


##Kerbereros

####kerberos.caches()
Returns a list of cached credentials. Can optionally specify `kerberos.caches(details=True)` to get extra details

####kerberos.principal_fromcache()
Returns the principal from and existing cache or returns None if no cache exists
