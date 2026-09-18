# رفع مشکل ظاهر خراب/بدون استایل روی سرور بدون اینترنت

## علت مشکل
برنامه از CDN اینترنتی برای Bootstrap، آیکون‌ها، فونت فارسی Vazirmatn و کتابخانه نمودار (vis-network) استفاده می‌کرد. **این وابستگی مربوط به مرورگر است، نه پکیج‌های pip.** روی سروری که نه خودش و نه کامپیوتری که با آن به برنامه وصل می‌شوید به اینترنت دسترسی ندارد، مرورگر نمی‌تواند این فایل‌ها را از CDN بگیرد و صفحه بدون استایل (HTML خام) نمایش داده می‌شود.

قالب‌های پروژه (`base.html`, `diagram.html`) اصلاح شده‌اند تا این فایل‌ها را از پوشه `static/vendor/` (لوکال، داخل خود پروژه) بارگذاری کنند. فقط کافی‌ست فایل‌ها را داخل این پوشه‌ها قرار دهید.

## مراحل

روی یک سیستم **با اینترنت**، این فایل‌ها را دانلود کرده و داخل ساختار زیر در پروژه (پوشه `dcam/static/vendor/`) کپی کنید:

```
static/vendor/
  bootstrap/
    bootstrap.rtl.min.css
    bootstrap.bundle.min.js
  bootstrap-icons/
    bootstrap-icons.css
    fonts/
      bootstrap-icons.woff
      bootstrap-icons.woff2
  vazirmatn/
    Vazirmatn-font-face.css
    fonts/   <-- فایل‌های فونت داخل zip رسمی Vazirmatn، همراه با ساختار پوشه‌شان کپی شود
  vis-network/
    vis-network.min.js
```

### لینک‌های دانلود (روی سیستم متصل به اینترنت باز کنید)

1. **Bootstrap 5.3.3 (RTL)**
   - CSS: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css`
   - JS: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js`

2. **Bootstrap Icons 1.11.3**
   - بهترین روش: دانلود کل پکیج از GitHub Releases:
     `https://github.com/twbs/icons/releases/download/v1.11.3/bootstrap-icons-1.11.3.zip`
     پس از اکسترکت، فایل `bootstrap-icons.css` و پوشه `font/fonts/` (دو فایل woff/woff2) را داخل `bootstrap-icons/` و `bootstrap-icons/fonts/` کپی کنید. (توجه: مسیرهای داخل css با `url("./fonts/...")` هستند، پس پوشه fonts باید کنار خود css باشد.)

3. **فونت Vazirmatn 33.0.3**
   - پکیج کامل: `https://github.com/rastikerdar/vazirmatn/releases/download/v33.0.3/vazirmatn-v33.0.3.zip`
   - از داخل zip، فایل `Vazirmatn-font-face.css` (از پوشه `fonts/webfonts` یا مشابه) و کل پوشه فونت‌های کنارش را با همان ساختار نسبی کپی کنید تا مسیرهای `url()` داخل css درست کار کنند.

4. **vis-network 9.1.9**
   - `https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js`

## انتقال به سرور
پوشه تکمیل‌شده `static/vendor/` را داخل پروژه روی macOS جایگزین کنید. نیازی به نصب یا کامپایل این فایل‌های استاتیک نیست.

بعد از این کار، برنامه را ری‌استارت کنید و صفحه را Refresh (Ctrl+F5) کنید تا کش مرورگر پاک شود.

## نکته
اگر ترجیح می‌دهید کاملاً ساده‌تر پیش بروید و فعلاً فقط ظاهر خام برایتان مهم نیست (چون سیستم کار می‌کند)، می‌توانید فعلاً از همین حالت استفاده کنید — عملکرد (ورود، ثبت اطلاعات، نمودار) درست کار می‌کند، فقط ظاهر ساده است.
