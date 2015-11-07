# -*- coding: utf-8 -*-
#
#  main.py
#  ShareMounter
#
#  Created by Mr. Kyle Crawshaw on 9/27/15.
#  Copyright (c) 2015 Kyle Crawshaw. All rights reserved.
#

# import modules required by application
import objc
import Foundation
import AppKit

from PyObjCTools import AppHelper

# import modules containing classes required to start application and load MainMenu.nib
import AppDelegate
import StatusBarController

# pass control to AppKit
AppHelper.runEventLoop()
