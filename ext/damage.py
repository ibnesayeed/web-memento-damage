'''
Section 'Damage' =============================================================
'''
import math
import os

from PyQt4.QtNetwork import QNetworkReply

from PIL import Image


def rgb2hex(r, g, b):
    return '{:02x}{:02x}{:02x}'.format(r, g, b).upper()

class SiteDamage:
    image_importance = {}
    css_importance = 0

    multimedia_weight   = 0.50
    css_weight          = 0.05
    proportion          = 3.0/4.0
    image_weight        = proportion * (1-(multimedia_weight + css_weight))
    text_weight         = 1 -(multimedia_weight + css_weight + image_weight)
    words_per_image     = 1000

    def __init__(self, images_log, csses_log, screenshot_file,
                 background_color = 'FFFFFF'):
        self.images_log = images_log
        self.csses_log = csses_log
        self.screenshot_file = os.path.abspath(screenshot_file)
        self.background_color = background_color

        self.get_missing_urls()

    def get_missing_urls(self):
        self.missing_imgs_log = []
        for log in self.images_log:
            status_code, true = log['status_code']
            if status_code > 399:
                self.missing_imgs_log.append(log)

        self.missing_csses_log = []
        for log in self.csses_log:
            if 'status_code' in log:
                status_code, true = log['status_code']
                if status_code > 399:
                    self.missing_csses_log.append(log)

    def calculate_potential_damage(self):
        total_image_damage = 0
        for log in self.missing_imgs_log:
            image_damage = self.calculate_image_damage(log)

            # Based on measureMemento.pl line 463
            for damage in image_damage:
                total_image_damage += damage

        total_css_damage = 0
        for url in self.missing_csses_log:
            css_damage = self.calculate_css_damage(log, is_potential=True)

            # Based on measureMemento.pl line 468
            total_css_damage += css_damage

        # Based on measureMemento.pl line 555
        final_image_damage = total_image_damage * self.image_weight
        final_css_damage = total_css_damage * self.css_weight
        total_damage = final_image_damage + final_css_damage

        return total_damage

    def calculate_actual_damage(self):
        total_image_damage = 0
        for log in self.missing_imgs_log:
            image_damage = self.calculate_image_damage(log)

            # Based on measureMemento.pl line 463
            for damage in image_damage:
                total_image_damage += damage

        total_css_damage = 0
        for url in self.missing_csses_log:
            css_damage = self.calculate_css_damage(log)

            # Based on measureMemento.pl line 468
            total_css_damage += css_damage

        # Based on measureMemento.pl line 555
        final_image_damage = total_image_damage * self.image_weight
        final_css_damage = total_css_damage * self.css_weight
        total_damage = final_image_damage + final_css_damage

        return total_damage

    def calculate_image_damage(self, log, size_weight=0.5,
                               centrality_weight=0.5):
        importances = []

        # A line in *.img.log representate an image
        # An image can be appeared in more than one location in page
        # Location and size is saved in 'rectangles'
        for image_rect in log['rectangles']:
            # Based on measureMemento.pl line 690
            x = image_rect['left']
            y = image_rect['top']
            w = image_rect['width']
            h = image_rect['height']

            im = Image.open(self.screenshot_file)
            viewport_w, viewport_h = im.size
            middle_x = viewport_w / 2
            middle_y = viewport_h / 2

            location_importance = 0
            # Based on measureMemento.pl line 703
            if (x + w) > middle_x and x < middle_x:
                location_importance += centrality_weight / 2;

            # Based on measureMemento.pl line 715
            if (y + h) > middle_y and y < middle_y:
                location_importance += centrality_weight / 2;

            prop = (w * h) / (viewport_w * viewport_h)
            size_importance = prop * size_weight

            importance = location_importance + size_importance
            importances.append(importance)

        return importances

    def calculate_css_damage(self, log, tag_weight=0.5, ratio_weight=0.5,
                             is_potential=False, use_window_size = True,
                             window_size=(1024,768)):
        css_url = log['url']
        tag_importance = log['importance']
        status_code, true =  log['status_code']

        # Based on measureMemento.pl line 760
        if status_code == 200:
            return 1

        # If status_code is started with 3xx
        # Based on measureMemento.pl line 764
        if str(status_code)[0] == '3':
            return 0

        importance = 0

        # Based on measureMemento.pl line 771
        if tag_importance > 0:
            importance += tag_weight

        # Based on measureMemento.pl line 777
        if not is_potential:
            # Code below is a subtitution for Justin's whitespace.pl
            # Open screenshot file
            im = Image.open(self.screenshot_file)
            # Get all pixels
            pix = im.load()

            # Use vieport_size (screenshot size) or default_window_size (
            # 1024x768)
            if not use_window_size:
                window_size = im.size()

            window_w, windows_h = window_size

            # Whiteguys is representation of pixels having same color with
            # background color
            whiteguys_col = {}

            # Iterate over pixels in window size (e.g. 1024x768)
            # And check whether having same color with background
            for x in range(0,window_w):
                for y in range(0,windows_h):
                    # Get RGBA color in each pixel
                    #     (e.g. White -> (255,255,255,255))
                    r_, g_, b_, a_ = pix[x,y]
                    # Convert RGBA to Hex color
                    #     (e.g. White -> FFFFFF)
                    pix_hex = rgb2hex(r_, g_, b_)

                    if pix_hex.upper() == self.background_color.upper():
                        whiteguys_col.setdefault(x, 0)
                        whiteguys_col[x] += 1

            # divide width into 3 parts
            # Justin use term : low, mid, and high for 1/3 left,
            # 1/3 midlle, and 1/3 right
            one_third = math.floor(window_w/3)

            # calculate whiteguys in the 1/3 left
            leftWhiteguys = 0
            for c in range(0,one_third):
                leftWhiteguys += whiteguys_col[c]
            leftAvg = leftWhiteguys / one_third

            # calculate whiteguys in the 1/3 center
            centerWhiteguys = 0
            for c in range(one_third,2*one_third):
                centerWhiteguys += whiteguys_col[c]
            centerAvg = centerWhiteguys / one_third

            # calculate whiteguys in the 1/3 right
            rightWhiteguys = 0
            for c in range(2*one_third,window_w):
                rightWhiteguys += whiteguys_col[c]
            rightAvg = rightWhiteguys / one_third

            # Based on measureMemento.pl line 803
            if (leftAvg + centerAvg + rightAvg) == 0:
                importance += 0
            elif float(rightAvg / (leftAvg+centerAvg+rightAvg)) > \
                    float(1/3):
                importance += float(rightAvg / (
                    leftAvg+centerAvg+rightAvg)) * ratio_weight
            else:
                importance += ratio_weight


        # Based on measureMemento.pl line 819
        else:
            importance += ratio_weight

        return importance