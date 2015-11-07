**NOTE: THIS PROJECT IS UNDER HEAVY DEVELOPMENT AND SHOULD NOT BE USED IN PRODUCTION YET.**

***

****Usage****

Run the following commands
- `git clone https://github.com/kylecrawshaw/ShareMounter.git`
- `cd /path/to/ShareMounter`
- `xcodebuild`
- `open build/Release/`



****About****

The goal of ShareMounter is to automatically map and mount network file shares for users based on Active Directory group membership. ShareMounter is a menu bar app that users can customize to their liking.

When the application is first launched it will check whether or not the domain is reachable. If it is, ShareMounter will get the group membership for the currently logged in user and compare group membership to the admin provided servers found in `/Library/Preferences/ShareMounter.plist` (example below). After determining available shares for the current user the menu will be displayed with the list of shares. ShareMounter will then start to watch for network state changes.

- If the domain cannot be reached all shares will be hidden.
- If a network share is set to `connect_automatically` it will be automatically mounted on launch or on network state change.
- When a user first launches the application their preferences and available shares are save to `~/Library/Preferences/ShareMounter.plist`

You can optionally launch this application as a LaunchAgent so that it will be run when each user logs in.


Feedback and pull requests are welcome!

****Requirements****
- Computer must be bound to Active Directory (for now...)
- System Admins should supply a list of network shares with titles and allowed AD groups
	-	`/Library/Preferences/ShareMounter.plist`
- Required keys for each share:
	- `share_url`
	- `title`
	- `groups`
- Optional keys:
	- `hide_from_menu`
	- `connect_automatically`

****Example plist****
```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>include_smb_home</key>
	<true />
	<key>network_shares</key>
	<array>
		<dict>
			<key>groups</key>
			<array>
				<string>Domain Admins</string>
				<string>IT</string>
			</array>
			<key>share_url</key>
			<string>smb://server1.example.com/Share1</string>
			<key>title</key>
			<string>Share1</string>
		</dict>
		<dict>
			<key>groups</key>
			<array>
				<string>Domain Admins</string>
				<string>DevelopmentOffice</string>
			</array>
			<key>share_url</key>
			<string>smb://server2.example.com/Development</string>
			<key>title</key>
			<string>Development</string>
		</dict>
	</array>
</dict>
</plist>
```

****Credits****

ShareMounter was inspired by a number of projects from these fine individuals
- Michael Lynn (aka pudquick, frogor, mikeymikey) -- mount_shares_better.py
- Graham Gilbert -- Imagr
- Peter Bukowinski -- KerbMinder
- Ben Toms (aka Macmule) -- Many blogposts and scripts

****Problems?****

Open and issue or better yet, submit a pull request with the fix. I want to make this as versatile of a tool as possible.
