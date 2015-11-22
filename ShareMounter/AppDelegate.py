# -*- coding: utf-8 -*-
#
#  AppDelegate.py
#  ShareMounter
#
#  Created by Mr. Kyle Crawshaw on 9/27/15.
#  Copyright (c) 2015 Kyle Crawshaw. All rights reserved.
#

from Foundation import *
from AppKit import *
import objc

class AppDelegate(NSObject):

    statusBarController = objc.IBOutlet()

    def applicationDidFinishLaunching_(self, notification):
        NSLog("Application did finish launching.")
        if self.statusBarController:
            self.statusBarController.runStartup()
        nc = NSUserNotificationCenter.defaultUserNotificationCenter()
        nc.setDelegate_(self)

    def userNotificationCenter_shouldPresentNotification_(self, center, notification):
        return objc.YES

    def applicationWillTerminate_(self, notification):
       # be nice and remove our observers from NSWorkspace
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.removeObserver_(self.statusBarController)
        self.statusBarController.releaseStatusBar()
