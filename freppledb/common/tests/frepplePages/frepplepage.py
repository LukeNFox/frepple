#
# Copyright (C) 2013 by frePPLe bv
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from freppledb.common.tests.frepplePages.freppleelement import (
    BasePageElement,
)
from freppledb.common.tests.frepplePages.frepplelocators import (
    TableLocators,
    BasePageLocators,
)

import time

import selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains

from django.conf import settings
from django.utils.formats import date_format

### Special page for common actions only


class SupplierEditInputElement(BasePageElement):
    locator = "input[id=id_name]"


class BasePage:
    NAV_MENU_LEFT = (
        "Sales",
        "Inventory",
        "Capacity",
        "Purchasing",
        "Manufacturing",
        "Admin",
        "My Reports",
        "Help",
    )

    def __init__(self, driver, testclass):
        self.driver = driver
        self.testclass = testclass

    def login(self, user="admin", password="admin"):
        self.open("/")
        if (
            "freppledb.common.middleware.AutoLoginAsAdminUser"
            not in settings.MIDDLEWARE
        ):
            self.driver.find_element(By.NAME, "username").send_keys(user)
            self.driver.find_element(By.NAME, "password").send_keys(password)
            self.driver.find_element(By.CSS_SELECTOR, "[type='submit']").click()

    def wait(self, timing):
        return WebDriverWait(self.driver, timing)

    def go_to_target_page_by_menu(self, menu_item, submenu_item):
        (menuby, menulocator) = BasePageLocators.mainMenuLinkLocator(menu_item)
        self.menuitem = self.driver.find_element(menuby, menulocator)
        ActionChains(self.driver).move_to_element(self.menuitem).perform()

        (submenuby, submenulocator) = BasePageLocators.subMenuItemLocator(submenu_item)
        self.submenuitem = self.driver.find_element(submenuby, submenulocator)
        time.sleep(1)
        ActionChains(self.driver).move_to_element(self.submenuitem).click().perform()
        time.sleep(1)

    def go_home_with_breadcrumbs(self):
        pass

    def go_back_to_page_with_breadcrumbs(self, targetPageName):
        pass

    def open(self, url):
        return self.driver.get("%s%s" % (self.testclass.live_server_url, url))


# create a table page class
# for all interactions with table
# ability to choose a specific table to interact with
# selecting a cell, updating a cell, reading value of a cell
class TablePage(BasePage):
    # purchase order page action method come here

    # declaring variable that will contain the retrieved table
    table = None

    def get_table(self):
        if not self.table:
            self.table = self.driver.find_element(*TableLocators.TABLE_DEFAULT)
        return self.table

    def get_table_row(self, rowNumber):
        table = self.get_table()
        rows = table.find_elements(*TableLocators.TABLE_ROWS)
        return rows[rowNumber]

    def get_table_multiple_rows(self, rowNumber):
        table = self.get_table()
        rows = table.find_elements(*TableLocators.TABLE_ROWS)
        return rows[1 : rowNumber + 1]

    def get_item_reference_in_target_row(self, targetrow):
        reference = targetrow.get_attribute("id")
        return reference

    def get_content_of_row_column(self, rowElement, columnName):
        content = rowElement.find_element(*TableLocators.tablecolumns[columnName])
        return content

    def click_target_row_colum(
        self, rowElement, columnNameLocator
    ):  # method that clicks of the table cell at the targeted row and column
        targetTableCell = self.get_content_of_row_column(rowElement, columnNameLocator)
        ActionChains(self.driver).move_to_element_with_offset(
            targetTableCell, 1, 1
        ).click().perform()
        inputfield = targetTableCell.find_element(
            *TableLocators.tablecolumnsinput[columnNameLocator]
        )
        return inputfield

    def click_target_cell(
        self, targetcellElement, columnNameLocator
    ):  # method that clicks of the table cell at the targeted row and column
        ActionChains(self.driver).move_to_element_with_offset(
            targetcellElement, 1, 1
        ).click().perform()
        inputfield = targetcellElement.find_element(
            *TableLocators.tablecolumnsinput[columnNameLocator]
        )
        return inputfield

    def enter_text_in_inputfield(self, targetinputfield, text):
        targetinputfield.clear()
        time.sleep(0.3)
        targetinputfield.send_keys(text)
        time.sleep(0.3)
        targetinputfield.send_keys(Keys.RETURN)
        time.sleep(0.3)

    def enter_text_in_inputdatefield(self, targetinputdatefield, newdate):
        val = date_format(newdate, "DATETIME_FORMAT", use_l10n=False)
        targetinputdatefield.clear()
        time.sleep(0.3)
        targetinputdatefield.send_keys(val)
        time.sleep(0.3)
        targetinputdatefield.send_keys(Keys.RETURN)
        time.sleep(0.3)
        return val

    def click_save_button(self):
        save_button = self.driver.find_element(*TableLocators.TABLE_SAVE_BUTTON)
        ActionChains(self.driver).move_to_element(save_button).click().perform()

    def click_undo_button(self):
        undo_button = self.driver.find_element(*TableLocators.TABLE_UNDO_BUTTON)
        ActionChains(self.driver).move_to_element(undo_button).click().perform()

    def select_action(
        self, actionToPerform
    ):  # method that will select an action from the select action dropdown
        select = self.driver.find_element(*TableLocators.TABLE_SELECT_ACTION)
        ActionChains(self.driver).move_to_element(select).click().perform()
        time.sleep(1)
        select_menu = self.driver.find_element(*TableLocators.TABLE_SELECT_ACTION_MENU)
        select_action = select_menu.find_element(
            *TableLocators.actionLocator(actionToPerform)
        )
        select_action.click()

    def multiline_checkboxes_check(
        self, targetrows
    ):  # method that will check a certain number of checkboxes in the checkbox column

        for row in targetrows:
            checkbox = row.find_element(*TableLocators.tablecolumnsinput["checkbox"])
            ActionChains(self.driver).move_to_element(checkbox).click().perform()
            time.sleep(0.3)
