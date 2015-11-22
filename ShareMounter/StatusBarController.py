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
from pymacad import *
import PyDialog
import CoreFoundation
import subprocess


class StatusBarController(NSObject):
    '''Main controller object for UI features'''
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
    # useSSOCheckbox = objc.IBOutlet()
    # loginButton = objc.IBOutlet()

    passwordPanel = objc.IBOutlet()
    passwordFieldLogin = objc.IBOutlet()
    passwordPanelView = objc.IBOutlet()
    usernameFieldLogin = objc.IBOutlet()
    serverNameLabel = objc.IBOutlet()

    menu_is_updating = False
    config_manager = SMUtilities.ConfigManager()


    def runStartup(self):
        self.statusBar = NSStatusBar.systemStatusBar().statusItemWithLength_(-1.0)
        statusBarImage = NSImage.imageNamed_('DefaultStatusBarIcon')
        statusBarImage.setTemplate_(True)
        self.statusBar.button().setImage_(statusBarImage)
        self.buildMainMenu()
        self.updateConfig()
        self.ldap_reachable = SMUtilities.is_ldap_reachable(SMUtilities.read_pref('domain'))
        self.registerForWorkspaceNotifications()
        self.detect_network_changes()


    def updateConfig(self):
        self.config_manager.validate_kerberos()
        self.ldap_reachable = SMUtilities.is_ldap_reachable(SMUtilities.read_pref('domain'))
        if self.ldap_reachable:
            self.config_manager.update_managedshares()
        self.buildConnectMenu()
        SMUtilities.notify('Connect menu has been updated!', '')


    @objc.IBAction
    def manualUpdate_(self, sender):
        self.ldap_reachable = SMUtilities.is_ldap_reachable(SMUtilities.read_pref('domain'))
        if self.ldap_reachable:
            self.updateConfig()
        else:
            d = PyDialog.AlertDialog('Unable to update Connect menu!', 'Domain cannot be reached...')
            d.display()


    @objc.IBAction
    def quit_(self, sender):
        # self.config_manager.save_prefs()
        app = NSApplication.sharedApplication()
        app.terminate_(objc.nil)


    def buildMainMenu(self):
        self.mainMenu = NSMenu.alloc().init()
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Loading...', None, '').setTarget_(self)
        self.mainMenu.addItem_(NSMenuItem.separatorItem())
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Manage Network Shares', self.manageNetworkShares_, '').setTarget_(self)
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Ticket Viewer', self.openTicketViewer_, '').setTarget_(self)
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Refresh Kerberos', self.refreshKerberosTicket_, '').setTarget_(self)
        self.mainMenu.addItem_(NSMenuItem.separatorItem())
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Show Shares on Desktop', self.toggleShowDrivesOnDesktop_, '').setTarget_(self)
        if CoreFoundation.CFPreferencesCopyAppValue('ShowMountedServersOnDesktop', 'com.apple.finder'):
            self.mainMenu.itemWithTitle_('Show Shares on Desktop').setState_(True)
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Display Notifications', self.toggleNotifications_, '').setTarget_(self)
        if SMUtilities.read_pref('display_notifications'):
            self.mainMenu.itemWithTitle_('Display Notifications').setState_(True)
        self.mainMenu.addItem_(NSMenuItem.separatorItem())
        self.mainMenu.addItemWithTitle_action_keyEquivalent_('Quit', self.quit_, '').setTarget_(self)
        self.statusBar.setMenu_(self.mainMenu)


    @objc.IBAction
    def openTicketViewer_(self, sender):
        app_path = '/System/Library/CoreServices/Ticket Viewer.app'
        NSWorkspace.sharedWorkspace().launchApplication_('Ticket Viewer')


    @objc.IBAction
    def refreshKerberosTicket_(self, sender):
        self.ldap_reachable = SMUtilities.is_ldap_reachable(SMUtilities.read_pref('domain'))
        if self.ldap_reachable:
            self.config_manager.validate_kerberos()
        else:
            d = PyDialog.AlertDialog('Unable to refresh Kerberos Ticket!', 'Domain cannot be reached...')
            d.display()


    def releaseStatusBar(self):
        self.mainMenu.release()
        NSStatusBar.systemStatusBar().removeStatusItem_(self.statusBar)
        self.statusBar.release()


    def buildShareMenu(self, share):
        user_added_shares = SMUtilities.get_user_added_shares()
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
        if share in user_added_shares:
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
        managed_shares = SMUtilities.get_managed_shares()
        if managed_shares == []:
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('No available shares...', None, '')
        else:
            for share in managed_shares:
                share_menu = self.buildShareMenu(share)
                self.connectMenu.addItem_(share_menu)
                if share.get('hide_from_menu'):
                    share_menu.setHidden_(True)
        if self.ldap_reachable:
            hide_all = False
            cannot_locate = self.connectMenu.itemWithTitle_('Cannot locate domain')
            if cannot_locate:
                cannot_locate.setHidden_(True)
        else:
            NSLog('Could not locate servers added to menu')
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('Cannot locate domain', None, '')
            hide_all = True


    def processUserAddedShares(self):
        user_added_shares = SMUtilities.get_user_added_shares()
        self.connectMenu.addItem_(NSMenuItem.separatorItem())
        if user_added_shares:
            no_available_shares = self.connectMenu.indexOfItemWithTitle_('No available shares...')
            if no_available_shares != -1:
                self.connectMenu.removeItemAtIndex_(no_available_shares)
            for share in user_added_shares:
                share_menu = self.buildShareMenu(share)
                self.connectMenu.addItem_(share_menu)
                if share.get('hide_from_menu'):
                    share_menu.setHidden_(True)
        self.connectMenu.addItem_(NSMenuItem.separatorItem())
        if self.ldap_reachable:
            hide_all = False
            self.connectMenu.addItemWithTitle_action_keyEquivalent_('Show Hidden', self.toggleShowHidden_, '').setTarget_(self)
            self.connectMenu.itemWithTitle_('Show Hidden').setHidden_(True)
            self.toggleShowHiddenButton()
        else:
            hide_all = True
        self.connectMenu.addItemWithTitle_action_keyEquivalent_('Check For Updates', self.manualUpdate_, '').setTarget_(self)
        for shareMenu in self.connectMenu.itemArray():
            if shareMenu.submenu() and hide_all:
                shareMenu.setHidden_(True)

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
        managed_shares = SMUtilities.get_managed_shares()
        user_added_shares = SMUtilities.get_user_added_shares()
        if self.ldap_reachable:
            for share in managed_shares:
                if (share.get('connect_automatically')
                    and share.get('mount_point')
                    not in SMUtilities.get_mounted_network_volumes()):

                    NSLog('Automounting {0}'.format(share.get('share_url')))
                    SMUtilities.mount_share(share.get('share_url'))
            for share in user_added_shares:
                if (share.get('connect_automatically')
                    and share.get('mount_point')
                    not in SMUtilities.get_mounted_network_volumes()):
                    SMUtilities.mount_share(share.get('share_url'))


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
        NSLog('User clicked {}'.format(sender.title()))
        try:
            share_title = sender.parentItem().title()
        except AttributeError:
            share_title = self.shareTitleField.stringValue()
        network_share = self.config_manager.get_sharebykey('title', share_title)
        if network_share.get('mount_point') in SMUtilities.get_mounted_network_volumes():
            d = PyDialog.AlertDialog('Cannot mount "{0}"'.format(network_share.get('title')),
                                     'Volume is already mounted at "{0}"'.format(network_share.get('mount_point')))
            d.display()
        else:
            SMUtilities.mount_share(network_share.get('share_url'))


    def getAvailableShares(self):
        available_shares = list()
        managed_shares = SMUtilities.get_managed_shares()
        user_added_shares = SMUtilities.get_user_added_shares()
        for share in managed_shares:
            share = dict(share)
            share['share_type'] = 'managed'
            available_shares.append(share)
        for share in user_added_shares:
            share = dict(share)
            share['share_type'] = 'user'
            available_shares.append(share)
        return available_shares


    @objc.IBAction
    def closePasswordPanel_(self, sender):
        self.passwordPanel.orderOut_(self)


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
        available_shares = self.getAvailableShares()
        self.networkSharesDropdown.removeAllItems()
        # if available_shares:
        #     network_share_titles = [share.get('title') for share in available_shares]
        # else:
        #     network_share_titles = list()
        # print 'SETTING UP MANAGED SHARES WINDOW'
        # self.networkSharesDropdown.removeAllItems()
        # self.networkSharesDropdown.addItemsWithTitles_(network_share_titles)
        self.setupManageShareWindow(refresh_shares=True)


    @objc.IBAction
    def changeVisibleShare_(self, sender):
        self.setupManageShareWindow()
    #
    # @objc.IBAction
    # def useSSOToggled_(self, sender):
    #     if self.useSSOCheckbox.state():
    #         self.loginButton.setHidden_(True)
    #     else:
    #         self.loginButton.setHidden_(False)


    @objc.IBAction
    def addNewShareClicked_(self, sender):
        self.shareTitleField.setStringValue_('New Share')
        self.shareTitleField.setEnabled_(True)
        self.shareURLField.setStringValue_('')
        self.shareURLField.setEnabled_(True)
        # self.useSSOCheckbox.setEnabled_(True)
        # self.useSSOCheckbox.setState_(False)
        self.hideFromMenuCheck.setState_(False)
        self.connectAutoCheck.setState_(False)
        self.networkSharesDropdown.addItemsWithTitles_(['New Share'])
        self.networkSharesDropdown.selectItemWithTitle_('New Share')
        self.removeButton.setHidden_(False)
        # self.loginButton.setHidden_(False)

    @objc.IBAction
    def saveButtonClicked_(self, sender):
        share_url = self.shareURLField.stringValue()
        share_title = self.shareTitleField.stringValue()
        auto_connect = True if self.connectAutoCheck.state() else False
        hide_from_menu = True if self.hideFromMenuCheck.state() else False
        selected_item = self.networkSharesDropdown.selectedItem()
        # use_kerberos = True if self.useSSOCheckbox.state() else False

        if share_title != selected_item.title():
            index = self.networkSharesDropdown.indexOfSelectedItem()
            self.networkSharesDropdown.removeItemAtIndex_(index)
            self.networkSharesDropdown.insertItemWithTitle_atIndex_(share_title, index)
            self.networkSharesDropdown.selectItemAtIndex_(index)

        share = self.config_manager.get_sharebykey('title', selected_item.title())
        if share:
            if share.get('share_type') in ['managed', 'smb_home']:
                existing_share, index = self.config_manager.get_managedshare_bykey('title', share.get('title'))
                existing_share['connect_automatically'] = auto_connect
                existing_share['hide_from_menu'] = hide_from_menu
                self.config_manager.update_share(existing_share, index)
            else:
                existing_share, index = self.config_manager.get_useradded_bykey('title', share.get('title'))
                existing_share['connect_automatically'] = auto_connect
                existing_share['hide_from_menu'] = hide_from_menu
                existing_share['title'] = share_title
                existing_share['share_url'] = share_url
                self.config_manager.update_share(existing_share, index)
                # self.config_manager.user_added_shares[existing_index]['use_kerberos'] = use_kerberos
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


    @objc.IBAction
    def removeUserShare_(self, sender):
        if sender.title() == 'Remove from Menu':
            share, index = self.config_manager.get_useradded_bykey('title', sender.parentItem().title())
        else:
            share, index = self.config_manager.get_useradded_bykey('title', self.shareTitleField.stringValue())
        menu_index = self.connectMenu.indexOfItemWithTitle_(share.get('title'))
        self.connectMenu.removeItemAtIndex_(menu_index)
        self.config_manager.remove_share(share)
        first_item = self.networkSharesDropdown.itemArray()[0]
        self.networkSharesDropdown.selectItemWithTitle_(first_item.title())
        if self.addShareWindow.isVisible():
            self.setupManageShareWindow(refresh_shares=True)


    @objc.IBAction
    def cancelButtonClicked_(self, sender):
        self.addShareWindow.orderOut_(self)


    def setupManageShareWindow(self, refresh_shares=False):
        available_shares = self.getAvailableShares()
        if available_shares:
            network_share_titles = [share.get('title') for share in available_shares]
            if refresh_shares:
                self.networkSharesDropdown.removeAllItems()
                self.networkSharesDropdown.addItemsWithTitles_(network_share_titles)

            if self.shareTitleField.stringValue() not in network_share_titles:
                refresh_shares=True
            selected_share_title = self.networkSharesDropdown.titleOfSelectedItem()


            selected_share = self.config_manager.get_sharebykey('title', selected_share_title)
            self.shareURLField.setStringValue_(selected_share.get('share_url'))
            self.shareTitleField.setStringValue_(selected_share.get('title'))
            if selected_share.get('share_type') in ['managed', 'smb_home']:
                self.shareTitleField.setEnabled_(False)
                self.shareURLField.setEnabled_(False)
                self.removeButton.setHidden_(True)
                # self.loginButton.setHidden_(True)
                # self.useSSOCheckbox.setEnabled_(False)
                # self.useSSOCheckbox.setState_(True)
                # self.loginButton.setHidden_(True)
            else:
                self.shareTitleField.setEnabled_(True)
                self.shareURLField.setEnabled_(True)
                self.removeButton.setHidden_(False)
                # self.useSSOCheckbox.setEnabled_(True)
                # if selected_share.get('use_kerberos') == 1:
                #     self.useSSOCheckbox.setState_(True)
                #     self.loginButton.setHidden_(True)
                # else:
                #     self.useSSOCheckbox.setState_(False)
                #     self.loginButton.setHidden_(False)

            self.hideFromMenuCheck.setState_(selected_share.get('hide_from_menu'))
            self.connectAutoCheck.setState_(selected_share.get('connect_automatically'))


    @objc.IBAction
    def toggleAutoConnect_(self, sender):
        share = self.config_manager.get_sharebykey('title', sender.parentItem().title())
        if share.get('share_type') in ['managed', 'smb_home']:
            existing_share, index = self.config_manager.get_managedshare_bykey('title', share.get('title'))
        else:
            existing_share, index = self.config_manager.get_useradded_bykey('title', share.get('title'))
        if existing_share:
            if existing_share.get('connect_automatically'):
                sender.setState_(False)
                existing_share['connect_automatically'] = False
                self.config_manager.update_share(existing_share, index)
                NSLog('User has set {0} to no longer connect automatically'.format(existing_share.get('title')))
            else:
                sender.setState_(True)
                existing_share['connect_automatically'] = True
                if existing_share.get('mount_point') not in SMUtilities.get_mounted_network_volumes():
                    SMUtilities.mount_share(existing_share.get('share_url'))
                self.config_manager.update_share(existing_share, index)
                NSLog('User has set {0} to connect automatically.'.format(existing_share.get('title')))
        if self.addShareWindow.isVisible():
            self.connectAutoCheck.setState_(share.get('connect_automatically'))


    @objc.IBAction
    def toggleHideShare_(self, sender):
        NSLog('User clicked "{0}"'.format(sender.title()))
        share = self.config_manager.get_sharebykey('title', sender.parentItem().title())
        if share.get('share_type') in ['managed', 'smb_home']:
            existing_share, index = self.config_manager.get_managedshare_bykey('title', share.get('title'))
        else:
            existing_share, index = self.config_manager.get_useradded_bykey('title', share.get('title'))
        if existing_share:
            if existing_share.get('hide_from_menu'):
                sender.parentItem().setHidden_(False)
                sender.setState_(False)
                existing_share['hide_from_menu'] = False
                self.config_manager.update_share(existing_share, index)
            else:
                if not self.connectMenu.itemWithTitle_('Show Hidden').state():
                    sender.parentItem().setHidden_(True)
                else:
                    sender.setState_(True)
                existing_share['hide_from_menu'] = True
                self.config_manager.update_share(existing_share, index)
        self.toggleShowHiddenButton()
        if self.addShareWindow.isVisible():
            self.hideFromMenuCheck.setState_(share.get('hide_from_menu'))


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

        alert = PyDialog.ContinueDialog(alert_title, message)
        alert.display()
        if alert.should_continue():
            CoreFoundation.CFPreferencesSetAppValue('ShowMountedServersOnDesktop', show_icons, finder)
            sender.setState_(show_icons)
            if CoreFoundation.CFPreferencesAppSynchronize(finder):
                subprocess.check_output(['/usr/bin/killall', '-HUP', 'Finder'])


    @objc.IBAction
    def toggleNotifications_(self, sender):
        if sender.state():
            show_notifications = False
        else:
            show_notifications = True
        sender.setState_(show_notifications)
        SMUtilities.write_pref('display_notifications', show_notifications)


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
                SMUtilities.unmount_share(mounted)
        else:
            network_share = self.config_manager.get_sharebykey('title', sender.parentItem().title())
            if network_share.get('mount_point') in mounted_volumes:
                SMUtilities.unmount_share(network_share.get('mount_point'))


    def unmountAllShares(self):
        mounted_volumes = SMUtilities.get_mounted_network_volumes()
        for mounted in mounted_volumes:
            SMUtilities.unmount_share(mounted)


    # def userNotificationCenter_shouldPresentNotification_(self, center, notification):
    #     return objc.YES


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


    def networkStateHasChanged(self, store, keys, info):
        NSLog('Network state has changed')
        self.ldap_reachable = SMUtilities.is_ldap_reachable(SMUtilities.read_pref('domain'))
        NSLog('Menu is updating: {0}'.format(self.menu_is_updating))
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
