# -*- coding: utf-8 -*-
#
#  StatusBarController.py
#  ShareMounter
#
#  Created by Mr. Kyle Crawshaw on 9/27/15.
#  Copyright (c) 2015 Kyle Crawshaw. All rights reserved.
#

from Foundation import *
from AppKit import *
from SystemConfiguration import *
import objc
import os
import SMUtilities
import CoreFoundation
import subprocess


class StatusBarController(NSObject):
    mainMenu = None
    connectMenu = None
    statusBar = None
    config = None
    user_config = None
    ldap_reachable = False
    shareURLField = objc.IBOutlet()
    shareTitleField = objc.IBOutlet()
    connectAutoCheck = objc.IBOutlet()
    hideFromMenuCheck = objc.IBOutlet()
    addShareWindow = objc.IBOutlet()
    manageSharesView = objc.IBOutlet()
    networkSharesDropdown = objc.IBOutlet()
    addNewButton = objc.IBOutlet()
    removeButton = objc.IBOutlet()
    doneButton = objc.IBOutlet()
    useSSOCheckbox = objc.IBOutlet()
    loginButton = objc.IBOutlet()


    passwordPanel = objc.IBOutlet()
    passwordFieldLogin = objc.IBOutlet()
    passwordPanelView = objc.IBOutlet()
    usernameFieldLogin = objc.IBOutlet()
    serverNameLabel = objc.IBOutlet()

    progressPanel = objc.IBOutlet()
    progressPanelBar = objc.IBOutlet()
    progressPanelLabel = objc.IBOutlet()

    menu_is_updating = False

    user = SMUtilities.DirectoryUser()
    kerberos = SMUtilities.Kerberos(user)
    config_manager = SMUtilities.ConfigManager()


    def runStartup(self):
        # self.ldap_reachable = SMUtilities.is_ldap_reachable(self.user.get_addomain())
        # if self.ldap_reachable:
        #     Utilities.kerberos_valid()
        #     self.config_manager.update_managedshares(self.user)
        self.statusBar = NSStatusBar.systemStatusBar().statusItemWithLength_(-1.0)
        statusBarImage = NSImage.imageNamed_('DefaultStatusBarIcon')
        statusBarImage.setTemplate_(True)
        self.statusBar.button().setImage_(statusBarImage)
        self.buildMainMenu()
        self.updateConfig()
        # self.buildConnectMenu()
        self.registerForWorkspaceNotifications()
        self.detect_network_changes()

    @objc.IBAction
    def quit_(self, sender):
        self.config_manager.save_prefs()
        app = NSApplication.sharedApplication()
        app.terminate_(objc.nil)

    def buildMainMenu(self):
        self.mainMenu = NSMenu.alloc().init()
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Loading...', None, '').setTarget_(self)
        self.mainMenu.addItem_(NSMenuItem.separatorItem())
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Manage Network Shares', self.manageNetworkShares_, '').setTarget_(self)
        self.mainMenu.addItem_(NSMenuItem.separatorItem())
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Show Shares on Desktop', self.toggleShowDrivesOnDesktop_, '').setTarget_(self)
        if CoreFoundation.CFPreferencesCopyAppValue('ShowMountedServersOnDesktop', 'com.apple.finder'):
            self.mainMenu.itemWithTitle_('Show Shares on Desktop').setState_(True)
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Display Notifications', self.toggleNotifications_, '').setTarget_(self)
        if self.config_manager.user_config.get('display_notifications'):
            self.mainMenu.itemWithTitle_('Display Notifications').setState_(True)
        self.mainMenu.addItem_(NSMenuItem.separatorItem())
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Quit', self.quit_, '').setTarget_(self)
        self.statusBar.setMenu_(self.mainMenu)

    def releaseStatusBar(self):
        self.mainMenu.release()
        # menu = nil;
        NSStatusBar.systemStatusBar().removeStatusItem_(self.statusBar)
        self.statusBar.release()
        # self.statusBar = None

    def buildShareMenu(self, share):
        # NSLog('Building menu for "{0}"'.format(share.get('title')))
        shareMenu = NSMenu.alloc().init()
        connectMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(share.get('title'), None, '')
        if share.get('mount_point') in SMUtilities.get_mounted_network_volumes():
            connectMenuItem.setState_(True)
            shareMenu.addItemWithTitle_action_keyEquivalent_('Unmount Share',
                                                             self.unmountShare_,
                                                             '').setTarget_(self)
            shareMenu.addItemWithTitle_action_keyEquivalent_('Open Folder',
                                                             self.openFolderClicked_,
                                                             '').setTarget_(self)
        else:
            connectMenuItem.setState_(False)
            shareMenu.addItemWithTitle_action_keyEquivalent_('Mount Share',
                                                             self.connectToShare_,
                                                             '').setTarget_(self)
        shareMenu.addItem_(NSMenuItem.separatorItem())
        shareMenu.addItemWithTitle_action_keyEquivalent_('Connect Automatically',
                                                         self.toggleAutoConnect_,
                                                         '').setTarget_(self)
        if share.get('connect_automatically'):
            shareMenu.itemWithTitle_('Connect Automatically').setState_(True)
        shareMenu.addItemWithTitle_action_keyEquivalent_('Hide from Menu',
                                                         self.toggleHideShare_,
                                                         '').setTarget_(self)
        if share in self.config_manager.user_added_shares:
            shareMenu.addItemWithTitle_action_keyEquivalent_('Remove from Menu',
                                                             self.removeUserShare_,
                                                             '').setTarget_(self)
        connectMenuItem.setSubmenu_(shareMenu)
        return connectMenuItem

    def updateShareMenu(self, share_path):
        mounted_volumes_base_paths = [os.path.basename(mounted) for mounted in SMUtilities.get_mounted_network_volumes()]
        share_menu_titles = [menu_item.title() for menu_item in self.connectMenu.itemArray()]
        network_share = self.config_manager.get_sharebykey('mount_point', share_path)
        if self.ldap_reachable:
            NSLog('Updating menu for "{0}"'.format(network_share.get('title')))
            item_index = self.connectMenu.indexOfItemWithTitle_(network_share.get('title'))
            self.connectMenu.removeItemAtIndex_(item_index)
            self.connectMenu.insertItem_atIndex_(self.buildShareMenu(network_share), item_index)
        # below updates the Umount All menu item
        for share in share_menu_titles:
            if share in mounted_volumes_base_paths:
                unmount_all = True
                break
            else:
                unmount_all = False
        unmount = self.connectMenu.itemWithTitle_('Unmount All')
        if unmount_all:
            unmount.setAction_(self.unmountShare_)
            unmount.setTarget_(self)
        else:
            unmount.setAction_(None)
            unmount.setTarget_(self)

    def processManagedShares(self):
        if self.config_manager.managed_shares == []:
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('No available shares...', None, '')
        else:
            for share in self.config_manager.managed_shares:
                share_menu = self.buildShareMenu(share)
                self.connectMenu.addItem_(share_menu)
                if share.get('hide_from_menu'):
                    share_menu.setHidden_(True)
        if self.ldap_reachable:
            hide_all = False
            cannot_locate = self.connectMenu.itemWithTitle_('Cannot locate servers')
            if cannot_locate:
                cannot_locate.setHidden_(True)
        else:
            NSLog('Could not locate servers added to menu')
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('Cannot locate servers', None, '')
            hide_all = True


    def processUserAddedShares(self):
        self.connectMenu.addItem_(NSMenuItem.separatorItem())
        if self.config_manager.user_added_shares:
            no_available_shares = self.connectMenu.indexOfItemWithTitle_('No available shares...')
            if no_available_shares != -1:
                self.connectMenu.removeItemAtIndex_(no_available_shares)
            for share in self.config_manager.user_added_shares:
                share_menu = self.buildShareMenu(share)
                self.connectMenu.addItem_(share_menu)
                if share.get('hide_from_menu'):
                    share_menu.setHidden_(True)

        if self.ldap_reachable:
            hide_all = False
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('Show Hidden', self.toggleShowHidden_, '').setTarget_(self)
            self.connectMenu.itemWithTitle_('Show Hidden').setHidden_(True)
            self.toggleShowHiddenButton()
        else:
            hide_all = True

        for shareMenu in self.connectMenu.itemArray():
            if shareMenu.submenu() and hide_all:
                shareMenu.setHidden_(True)

        # if len(self.connectMenu.itemArray()) > 3:
        self.connectMenu.addItem_(NSMenuItem.separatorItem())
        if SMUtilities.get_mounted_network_volumes():
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('Unmount All', self.unmountShare_, '').setTarget_(self)
        else:
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('Unmount All', None, '')

    def buildConnectMenu(self):
        self.menu_is_updating = True
        NSLog('building connectMenu')
        self.connectMenu = NSMenu.alloc().init()
        self.processManagedShares()
        self.processUserAddedShares()
        self.autoMountShares()
        if self.mainMenu.itemAtIndex_(0).title() == 'Loading...':
            self.mainMenu.removeItemAtIndex_(0)
            self.mainMenu.insertItemWithTitle_action_keyEquivalent_atIndex_('Connect', None, '', 0)
        self.mainMenu.itemWithTitle_('Connect').setSubmenu_(self.connectMenu)
        self.menu_is_updating = False
        NSLog('Connect menu has been updated.')

    def autoMountShares(self):
        if self.ldap_reachable:
            for share in self.config_manager.managed_shares:
                if (share.get('connect_automatically')
                    and share.get('mount_point')
                    not in SMUtilities.get_mounted_network_volumes()):

                    NSLog('Automounting {0}'.format(share.get('share_url')))
                    SMUtilities.mount_share(share.get('share_url'),
                                            self.config_manager.user_config.get('display_notifications'))
            for share in self.config_manager.user_added_shares:
                if (share.get('connect_automatically')
                    and share.get('mount_point')
                    not in SMUtilities.get_mounted_network_volumes()):
                    SMUtilities.mount_share(share.get('share_url'),
                                            self.config_manager.user_config.get('display_notifications'))

    def toggleShowHiddenButton(self):
        for connectMenuItem in self.connectMenu.itemArray():
            if connectMenuItem.isHidden() and not (connectMenuItem.title() == 'Show Hidden' or connectMenuItem.title() == 'Unmount All'):
                hide_menu_item = False
                break
            else:
                hide_menu_item = True
        if hide_menu_item and not self.connectMenu.itemWithTitle_('Show Hidden').state():
            self.connectMenu.itemWithTitle_('Show Hidden').setHidden_(True)
        else:
            self.connectMenu.itemWithTitle_('Show Hidden').setHidden_(False)


    @objc.IBAction
    def connectToShare_(self, sender):
        NSLog('User clicked {}'.format(sender.parentItem().title()))
        network_share = self.config_manager.get_sharebykey('title', sender.parentItem().title())
        if network_share.get('share_type') == 'user' and network_share.get('use_kerberos'):
            if network_share.get('username') == None:
                self.openPasswordPanel_(self)
            else:
                self.config_manager.check_keychain(network_share.get('share_url'),
                                                   network_share.get('username'))
        SMUtilities.mount_share(network_share.get('share_url'),
                                self.config_manager.user_config.get('display_notifications'))

    def getAvailableShares(self):
        available_shares = list()
        for share in self.config_manager.managed_shares:
            share['share_type'] = 'managed'
            available_shares.append(share)
        for share in self.config_manager.user_added_shares:
            share['share_type'] = 'user'
            available_shares.append(share)
        return available_shares

    @objc.IBAction
    def closePasswordPanel_(self, sender):
        print 'Close panel clicked'
        self.passwordPanel.orderOut_(self)

    @objc.IBAction
    def savePassword_(self, sender):
        share_url = self.shareURLField.stringValue()
        username = self.usernameFieldLogin.stringValue()
        password = self.passwordFieldLogin.stringValue()

        if self.config_manager.check_keychain(share_url, username):
            self.config_manager.delete_share_from_keychain(share_url, username)
        self.config_manager.add_share_to_keychain(share_url,
                                                  username,
                                                  password)

        network_share, index = self.config_manager.get_useradded_bykey('share_url',
                                                                self.shareURLField.stringValue())

        self.config_manager.user_added_shares[index]['username'] = username
        self.closePasswordPanel_(self)
        self.usernameFieldLogin.setStringValue_(''),
        self.passwordFieldLogin.setStringValue_('')
        self.config_manager.save_prefs()


    @objc.IBAction
    def openPasswordPanel_(self, sender):
        if self.shareURLField.stringValue() == '':
            d = SMUtilities.PyDialog.AlertDialog('Missing fields!',
                                                 'You must enter a url to the network share!')
            d.display()
        else:
            self.saveButtonClicked_(self)
            network_share, index = self.config_manager.get_useradded_bykey('share_url',
                                                                    self.shareURLField.stringValue())
            if network_share.get('username'):
                if (self.config_manager.check_keychain(network_share.get('share_url'),
                                                       network_share.get('username'))):
                    username = network_share.get('username')
                else:
                    username = ''
                self.usernameFieldLogin.setStringValue_(username)
            self.serverNameLabel.setStringValue_(network_share.get('share_url'))
            NSApplication.sharedApplication().activateIgnoringOtherApps_(objc.YES)
            self.passwordPanel.makeKeyAndOrderFront_(self)

    @objc.IBAction
    def manageNetworkShares_(self, sender):
        NSLog('User clicked {0}'.format(sender.title()))
        # setup positioning of window to be below statusbaritem
        status_button = self.statusBar.valueForKey_('window').frame()
        x = status_button.origin.x - self.addShareWindow.frame().size.width/2
        y = status_button.origin.y
        self.addShareWindow.setFrameOrigin_((x,y))
        # make application front and display window
        NSApplication.sharedApplication().activateIgnoringOtherApps_(objc.YES)
        self.addShareWindow.makeKeyAndOrderFront_(self)
        network_share_titles = [share.get('title') for share in self.getAvailableShares()]
        self.networkSharesDropdown.removeAllItems()
        self.networkSharesDropdown.addItemsWithTitles_(network_share_titles)
        self.setupManageShareWindow()

    @objc.IBAction
    def changeVisibleShare_(self, sender):
        self.setupManageShareWindow()

    @objc.IBAction
    def useSSOToggled_(self, sender):
        if self.useSSOCheckbox.state():
            self.loginButton.setHidden_(True)
        else:
            self.loginButton.setHidden_(False)

    @objc.IBAction
    def addNewShareClicked_(self, sender):
        self.shareTitleField.setStringValue_('New Share')
        self.shareTitleField.setEnabled_(True)
        self.shareURLField.setStringValue_('')
        self.shareURLField.setEnabled_(True)
        self.useSSOCheckbox.setEnabled_(True)
        self.useSSOCheckbox.setState_(False)
        self.hideFromMenuCheck.setState_(False)
        self.connectAutoCheck.setState_(False)
        self.networkSharesDropdown.addItemsWithTitles_(['New Share'])
        self.networkSharesDropdown.selectItemWithTitle_('New Share')
        self.removeButton.setHidden_(False)
        self.loginButton.setHidden_(False)

    @objc.IBAction
    def saveButtonClicked_(self, sender):
        share_url = self.shareURLField.stringValue()
        share_title = self.shareTitleField.stringValue()
        auto_connect = True if self.connectAutoCheck.state() else False
        hide_from_menu = True if self.hideFromMenuCheck.state() else False
        selected_item = self.networkSharesDropdown.selectedItem()
        use_kerberos = True if self.useSSOCheckbox.state() else False

        if share_title != selected_item.title():
            index = self.networkSharesDropdown.indexOfSelectedItem()
            self.networkSharesDropdown.removeItemAtIndex_(index)
            self.networkSharesDropdown.insertItemWithTitle_atIndex_(share_title, index)
            self.networkSharesDropdown.selectItemAtIndex_(index)

        existing_share = self.config_manager.get_sharebykey('title', selected_item.title())

        if existing_share:
            if existing_share.get('share_type') == 'managed':
                existing_index = self.config_manager.managed_shares.index(existing_share)
                self.config_manager.managed_shares[existing_index]['connect_automatically'] = auto_connect
                self.config_manager.managed_shares[existing_index]['hide_from_menu'] = hide_from_menu
            else:
                existing_index = self.config_manager.user_added_shares.index(existing_share)
                self.config_manager.user_added_shares[existing_index]['connect_automatically'] = auto_connect
                self.config_manager.user_added_shares[existing_index]['hide_from_menu'] = hide_from_menu
                self.config_manager.user_added_shares[existing_index]['title'] = share_title
                self.config_manager.user_added_shares[existing_index]['share_url'] = share_url
                self.config_manager.user_added_shares[existing_index]['use_kerberos'] = use_kerberos
            connect_menu_item = self.connectMenu.itemWithTitle_(selected_item.title())
            connect_menu_item.setTitle_(share_title)
            if self.ldap_reachable and not self.connectMenu.itemWithTitle_('Show Hidden').state():
                connect_menu_item.setHidden_(hide_from_menu)
            connect_submenu = connect_menu_item.submenu()
            connect_submenu.itemWithTitle_('Connect Automatically').setState_(auto_connect)
            connect_submenu.itemWithTitle_('Hide from Menu').setState_(hide_from_menu)
        else:
            self.config_manager.add_or_update_usershare(share_title, share_url,
                                                        hide_from_menu, auto_connect)
            self.buildConnectMenu()
        self.setupManageShareWindow()
        self.config_manager.save_prefs()


    @objc.IBAction
    def removeUserShare_(self, sender):
        if sender.title() == 'Remove from Menu':
            share, index = self.config_manager.get_useradded_bykey('title', sender.parentItem().title())
        else:
            share, index = self.config_manager.get_useradded_bykey('title', self.shareTitleField.stringValue())
        menu_index = self.connectMenu.indexOfItemWithTitle_(share.get('title'))
        self.connectMenu.removeItemAtIndex_(menu_index)
        self.config_manager.user_added_shares.remove(share)
        first_item = self.networkSharesDropdown.itemArray()[0]
        self.networkSharesDropdown.selectItemWithTitle_(first_item.title())
        if self.addShareWindow.isVisible():
            self.setupManageShareWindow(refresh_shares=True)
        self.config_manager.save_prefs()


    @objc.IBAction
    def cancelButtonClicked_(self, sender):
        self.addShareWindow.orderOut_(self)

    def setupManageShareWindow(self, refresh_shares=False):
        network_share_titles = [share.get('title') for share in self.getAvailableShares()]
        if self.shareTitleField.stringValue() not in network_share_titles:
            refresh_shares=True
        selected_share_title = self.networkSharesDropdown.titleOfSelectedItem()

        if refresh_shares:
            self.networkSharesDropdown.removeAllItems()
            self.networkSharesDropdown.addItemsWithTitles_(network_share_titles)
        selected_share = self.config_manager.get_sharebykey('title', selected_share_title)
        self.shareURLField.setStringValue_(selected_share.get('share_url'))
        self.shareTitleField.setStringValue_(selected_share.get('title'))
        if selected_share.get('share_type') == 'managed':
            self.shareTitleField.setEnabled_(False)
            self.shareURLField.setEnabled_(False)
            self.removeButton.setHidden_(True)
            self.loginButton.setHidden_(True)
            self.useSSOCheckbox.setEnabled_(False)
            self.useSSOCheckbox.setState_(True)
            self.loginButton.setHidden_(True)
        else:
            self.shareTitleField.setEnabled_(True)
            self.shareURLField.setEnabled_(True)
            self.removeButton.setHidden_(False)
            self.useSSOCheckbox.setEnabled_(True)
            if selected_share.get('use_kerberos') == 1:
                self.useSSOCheckbox.setState_(True)
                self.loginButton.setHidden_(True)
            else:
                self.useSSOCheckbox.setState_(False)
                self.loginButton.setHidden_(False)

        self.hideFromMenuCheck.setState_(selected_share.get('hide_from_menu'))
        self.connectAutoCheck.setState_(selected_share.get('connect_automatically'))


    @objc.IBAction
    def toggleAutoConnect_(self, sender):

        share = self.config_manager.get_sharebykey('title', sender.parentItem().title())
        if share:
            if share.get('connect_automatically'):
                sender.setState_(False)
                share['connect_automatically'] = False
                NSLog('User has set {0} to no longer connect automatically'.format(share.get('title')))
            else:
                sender.setState_(True)
                share['connect_automatically'] = True
                if share.get('mount_point') not in SMUtilities.get_mounted_network_volumes():
                    SMUtilities.mount_share(share.get('share_url'),
                                            self.config_manager.user_config.get('display_notifications'))
                NSLog('User has set {0} to connect automatically.'.format(share.get('title')))
        if self.addShareWindow.isVisible():
            self.connectAutoCheck.setState_(share.get('connect_automatically'))
        self.config_manager.save_prefs()

    @objc.IBAction
    def toggleHideShare_(self, sender):
        NSLog('User clicked "{0}"'.format(sender.title()))
        share = self.config_manager.get_sharebykey('title', sender.parentItem().title())
        print share
        if share:
            if share.get('hide_from_menu'):
                sender.parentItem().setHidden_(False)
                sender.setState_(False)
                share['hide_from_menu'] = False
            else:
                if not self.connectMenu.itemWithTitle_('Show Hidden').state():
                    sender.parentItem().setHidden_(True)
                else:
                    sender.setState_(True)
                share['hide_from_menu'] = True
        self.toggleShowHiddenButton()
        if self.addShareWindow.isVisible():
            self.hideFromMenuCheck.setState_(share.get('hide_from_menu'))
        self.config_manager.save_prefs()

    @objc.IBAction
    def toggleShowHidden_(self, sender):
        if sender.state():
            for shareMenu in self.connectMenu.itemArray():
                submenu = shareMenu.submenu()
                if submenu:
                    hidden_flag = submenu.itemWithTitle_('Hide from Menu').state()
                    if hidden_flag and sender.state():
                        shareMenu.setHidden_(True)
            sender.setState_(False)
        else:
            for shareMenu in self.connectMenu.itemArray():
                if shareMenu.isHidden() and sender.state() == False:
                    shareMenu.setHidden_(False)
                    shareMenu.submenu().itemWithTitle_('Hide from Menu').setState_(True)
            sender.setState_(True)

    @objc.IBAction
    def toggleShowDrivesOnDesktop_(self, sender):
        finder = 'com.apple.finder'
        message = ''''Finder has to be restarted for changes to take effect. \
                      Your desktop will flash for a moment'''

        if CoreFoundation.CFPreferencesCopyAppValue('ShowMountedServersOnDesktop', finder) and sender.state():
            show_icons = False
            alert_title = 'Getting ready to hide server icons on desktop.'
        else:
            show_icons = True
            alert_title = 'Getting ready to show server icons on desktop.'

        alert = SMUtilities.PyDialog.ContinueDialog(alert_title, message)
        alert.display()
        if alert.should_continue():
            CoreFoundation.CFPreferencesSetAppValue('ShowMountedServersOnDesktop', show_icons, finder)
            sender.setState_(show_icons)
            CoreFoundation.CFPreferencesAppSynchronize(finder)
            subprocess.check_output(['/usr/bin/killall', '-HUP', 'Finder'])

    @objc.IBAction
    def toggleNotifications_(self, sender):
        if sender.state():
            show_notifications = False
        else:
            show_notifications = True
        sender.setState_(show_notifications)
        self.config_manager.user_config['display_notifications'] = show_notifications
        self.config_manager.save_prefs()

    @objc.IBAction
    def openFolderClicked_(self, sender):
        share_title = sender.parentItem().title()
        share_to_open = self.config_manager.get_sharebykey('title', share_title)
        SMUtilities.open_file(share_to_open.get('mount_point'))


    @objc.IBAction
    def unmountShare_(self, sender):
        NSLog('User clicked {}'.format(sender.title()))
        mounted_volumes = SMUtilities.get_mounted_network_volumes()
        if sender.title() == 'Unmount All':
            for mounted in mounted_volumes:
                SMUtilities.unmount_share(mounted,
                                         self.config_manager.user_config.get('display_notifications'))
        else:
            network_share = self.config_manager.get_sharebykey('title', sender.parentItem().title())
            if network_share.get('mount_point') in mounted_volumes:
                SMUtilities.unmount_share(network_share.get('mount_point'),
                                         self.config_manager.user_config.get('display_notifications'))


    def unmountAllShares(self):
        mounted_volumes = SMUtilities.get_mounted_network_volumes()
        for mounted in mounted_volumes:
            SMUtilities.unmount_share(mounted,
                                     self.config_manager.user_config.get('display_notifications'))


    def userNotificationCenter_shouldPresentNotification_(self, center, notification):
        return objc.YES


    def registerForWorkspaceNotifications(self):
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        notifications = [NSWorkspaceDidMountNotification,
                         NSWorkspaceDidUnmountNotification]
        for n in notifications:
            nc.addObserver_selector_name_object_(self,
                                                 self.wsNotificationReceived,
                                                 n,
                                                 None)
        NSLog('Registered for Workspace Notifications')


    def wsNotificationReceived(self, notification):
        notification_name = notification.name()
        user_info = notification.userInfo()
        NSLog("NSWorkspace notification was: %@", notification_name)
        if notification_name == NSWorkspaceDidMountNotification:
            new_volume = user_info['NSDevicePath']
            NSLog("%@ was mounted", new_volume)
            update_volume = new_volume
        elif notification_name == NSWorkspaceDidUnmountNotification:
            removed_volume = user_info['NSDevicePath']
            NSLog("%@ was unmounted", removed_volume)
            update_volume = removed_volume
        elif notification_name == NSWorkspaceDidRenameVolumeNotification:
            update_volume = None

        network_share = self.config_manager.get_sharebykey('mount_point', update_volume)
        if update_volume and network_share:
            if self.connectMenu.itemWithTitle_(network_share.get('title')):
                self.updateShareMenu(update_volume)
            else:
                NSLog('Connect Menu is empty. No need to update')

    def updateConfig(self):
        self.ldap_reachable = SMUtilities.is_ldap_reachable(self.user.get_addomain())
        if self.ldap_reachable:
            self.kerberos.kerberos_valid()
            self.config_manager.update_managedshares(self.user)
        self.buildConnectMenu()

    def networkStateHasChanged(self, store, keys, info):
        NSLog('Network state has changed')
        self.ldap_reachable = SMUtilities.is_ldap_reachable(self.user.get_addomain())
        print 'Menu is updating: {0}'.format(self.menu_is_updating)
        if self.menu_is_updating == False:
            self.menu_is_updating = True
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(3.5,
                                                                                     self,
                                                                                     self.updateConfig,
                                                                                     None,
                                                                                     objc.NO)


    def detect_network_changes(self):
        store = SCDynamicStoreCreate(None,
                                     "global-network-watcher",
                                     self.networkStateHasChanged, None)
        SCDynamicStoreSetNotificationKeys(store,
                                          None,
                                          ['State:/Network/Global/IPv4'])
        CFRunLoopAddSource(CFRunLoopGetCurrent(),
                           SCDynamicStoreCreateRunLoopSource(None, store, 0),
                           kCFRunLoopCommonModes)
        CFRunLoopRun()
        NSLog('Started monitoring for network state changes...')
