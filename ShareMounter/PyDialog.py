from AppKit import NSTextField, NSMakeRect, NSSecureTextField, NSAlert, \
                   NSCriticalAlertStyle

class AlertDialog(object):

    def __init__(self, title, message):
        self.alert = NSAlert.alloc().init()
        self.alert.setTitle_andMessage_(title, message)
        self.button_return = None

    def display(self):
        self.button_return = self.alert.runModal()

class InputDialog(AlertDialog):

    def __init__(self, title, message):
        AlertDialog.__init__(self, title, message)
        self.input = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        self.alert.setAccessoryView_(self.input)

    def get_input(self):
        return self.input.stringValue()

class SecureInputDialog(InputDialog):

    def __init__(self, title, message):
        InputDialog.__init__(self, title, message)
        self.input = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 24))
        self.alert.setAccessoryView_(self.input)

class ContinueDialog(AlertDialog):

    def __init__(self, title, message):
        AlertDialog.__init__(self, title, message)
        self.alert.addButtonWithTitle_('OK')
        self.alert.addButtonWithTitle_('Cancel')
        self.alert.setAlertStyle_(NSCriticalAlertStyle)

    def should_continue(self):
        return True if self.button_return == 1000 else False
