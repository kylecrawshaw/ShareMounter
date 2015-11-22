**NOTE: THIS PROJECT IS UNDER HEAVY DEVELOPMENT AND SHOULD NOT BE USED IN PRODUCTION YET.**

***

***Usage***

[Download the latest release]('https://github.com/kylecrawshaw/ShareMounter/releases') of ShareMounter. The application will run standalone, but System Admins can also provide either a plist or mobileconfig profile with a list of network shares. ShareMounter is `defaults` aware and relies on `CFPreferences` to keep both managed and user preferences in sync.

ShareMounter can be run and installed on a Mac regardless of whether it is bound to Active Directory or not.


***About***

The goal of ShareMounter is to automatically map and mount network file shares for users based on Active Directory group membership. ShareMounter is a menu bar app that users can customize to their liking.

When the application is first launched it will check whether or not the domain is reachable. If it is, ShareMounter will get the group membership for the currently logged in user and compare group membership to the admin provided servers found in `/Library/Preferences/ShareMounter.plist` (example below). After determining available shares for the current user the menu will be displayed with the list of shares. ShareMounter will then start to watch for network state changes.

- If the domain cannot be reached all shares will be hidden.
- If a network share is set to `connect_automatically` it will be automatically mounted on launch or on network state change.
- When a user first launches the application their preferences and available shares are saved to `~/Library/Preferences/ShareMounter.plist`

You can optionally launch this application as a LaunchAgent so that it will be run when each user logs in.


Feedback and pull requests are welcome!

***Requirements***
- System Admins should supply a list of network shares with titles and allowed AD groups
	-	`/Library/Preferences/ShareMounter.plist`
	- `ShareMounter.mobileconfig`
- Required keys for each share:
	- `share_url`
	- `title`
	- `groups`
- Optional keys:
	- `hide_from_menu`
	- `connect_automatically`


***Example mobileconfig profile***
This example profile was generated using [MCXToProfile]('https://github.com/timsutton/mcxToProfile')
```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>PayloadContent</key>
	<array>
		<dict>
			<key>PayloadContent</key>
			<dict>
				<key>ShareMounter</key>
				<dict>
					<key>Forced</key>
					<array>
						<dict>
							<key>mcx_preference_settings</key>
							<dict>
								<key>include_smb_home</key>
								<true/>
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
						</dict>
					</array>
				</dict>
			</dict>
			<key>PayloadEnabled</key>
			<true/>
			<key>PayloadIdentifier</key>
			<string>MCXToProfile.704db073-425f-49be-8a4f-82b821a5b1ab.alacarte.customsettings.e10452e0-10f3-4e26-8d07-ad030d430cf9</string>
			<key>PayloadType</key>
			<string>com.apple.ManagedClient.preferences</string>
			<key>PayloadUUID</key>
			<string>e10452e0-10f3-4e26-8d07-ad030d430cf9</string>
			<key>PayloadVersion</key>
			<integer>1</integer>
		</dict>
	</array>
	<key>PayloadDescription</key>
	<string>Included custom settings:
ShareMounter

Git revision: a14a19d7f0</string>
	<key>PayloadDisplayName</key>
	<string>ShareMounter Managed Preferences</string>
	<key>PayloadIdentifier</key>
	<string>ShareMounter</string>
	<key>PayloadOrganization</key>
	<string></string>
	<key>PayloadRemovalDisallowed</key>
	<true/>
	<key>PayloadScope</key>
	<string>System</string>
	<key>PayloadType</key>
	<string>Configuration</string>
	<key>PayloadUUID</key>
	<string>704db073-425f-49be-8a4f-82b821a5b1ab</string>
	<key>PayloadVersion</key>
	<integer>1</integer>
</dict>
</plist>
```

***Example plist***
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

***Credits***

ShareMounter was inspired by a number of projects from these fine individuals
- Michael Lynn (aka pudquick, frogor, mikeymikey) -- mount_shares_better.py
- Graham Gilbert -- Imagr
- Peter Bukowinski -- KerbMinder
- Ben Toms (aka Macmule) -- Many blogposts and scripts

***Problems?***

Open an issue or better yet, submit a pull request with the fix. I want to make this as versatile of a tool as possible.
