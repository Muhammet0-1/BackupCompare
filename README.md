# Backup Compare

[English](README.en.md) · [Test kanıtı](TESTING.md)

[Yazı: Yedek klasörü var. Peki dosyalar aynı mı?](https://lordms.net/tr/yazilar/yedek-klasor-kontrolu/)

[Kullanım rehberi](https://lordms.net/tr/notlar/backup-compare-kullanim/)

Python standart kütüphanesiyle iki klasörün göreli yollarını ve dosya içeriklerini karşılaştıran, salt okunur komut satırı aracı. Dosya kopyalamaz, silmez, onarmaz; yedek oluşturmaz. Ek Python paketi veya hesap gerektirmez.

## Kullanım

Python 3.9+ hedeflenir. Python 3.9 en düşük uyumluluk hedefidir; bu taslakta doğrulanmış sürüm değildir.

```sh
python3 backup_compare.py "/kaynak/klasör" "/yedek/klasör"
python3 backup_compare.py "/kaynak/klasör" "/yedek/klasör" --json
```

Windows PowerShell'de Python başlatıcısı mevcutsa:

```powershell
py -3 backup_compare.py "C:\Ornek\Kaynak" "D:\Ornek\Yedek" --json
$LASTEXITCODE
```

Kökler mevcut ve ayrı dizinler olmalı; aynı veya birbirinin altında olamaz. Kök yol bileşenlerinde `..` kullanma. Önce sentetik geçici dizinlerde dene; kaynak ile yedek sırasını doğrula. Çıktıyı dosyaya yönlendireceksen raporu her iki kökün dışında tut.

## Sonuçlar

- `missing`: kaynakta olup yedekte olmayan dosya veya dizin.
- `extra`: yalnız yedekte bulunan dosya veya dizin; otomatik silme talimatı değildir.
- `different`: aynı yoldaki içerik veya öğe türü farklı.
- `same`: SHA256 özeti eşit düzenli dosyalar.
- `empty_directories`: boş dizinler ayrıca raporlanır. Buradaki `missing`, kaynaktaki boş dizin yolunun yedekte boş dizin olarak bulunmamasıdır; yedekte dolu olması da bu kapsamdadır. `extra` tersidir. `.` kökü gösterir.
- `issues` ve `complete`: hata/eksik kapsam değerlendirmesi.

Kod 0: tamamlandı, fark yok. Kod 1: tamamlandı, fark var. Kod 2: hata veya eksik inceleme; fark bulunsa bile önceliklidir. Kod 2'de tüm `same` listeleri boşaltılır; kalan bulgular kısmidir. Yanlış CLI kullanımı da kod 2 verir ve JSON üretmez. `same: []` tek başına dosyaların farklı olduğunu göstermez.

## Sınırlar

Her iki taraftaki bütün düzenli dosyalar 1 MiB parçalarla SHA256 için okunur; ortak yollar özetlerle karşılaştırılır. Sıfır bayt dosyalar da hash edilir. Sonuç ve tarama metadata'sı dosya sayısıyla büyür; dosya içeriği bütünüyle belleğe alınmaz.

Sembolik bağlantı/reparse point, özel dosya ve okunamayan öğeler eksik incelemeye yol açar. Köklerin üst bileşenleri de denetlenir. POSIX'te descriptor-relative O_NOFOLLOW koruması kullanılır. Windows/diğer yedek açma yolunda denetim-açma yarışı kalır; saldırganca eşzamanlı değiştirilen dosya sistemi için güvenlik sınırı veya mutlak bağlantı izlememe garantisi değildir.

Tarama atomik anlık görüntü almaz. Gözlenebilen dosya/dizin değişimleri denetlenir; gözlenemeyen veya son kontrolden sonraki değişim kaçabilir. Çok derin dizinler eksik/kod 2 olabilir. İşletim sistemi okuma sırasında atime güncelleyebilir. ACL, sahiplik, xattr, alternatif akış/resource fork, seyrek düzen ve hardlink topolojisi karşılaştırılmaz. Büyük/küçük harf veya Unicode normalleştirme yapılmaz.

Hash eşitliği SHA256'nın olağan çakışma varsayımına dayanır; geri yükleme veya uygulamanın açılması garantisi değildir. Gerçek geri yükleme ayrı konumda ayrıca denenmelidir. Paylaşılacak raporlar dosya adları/yolları içerebilir; yalnız sentetik veriyle tanıtım yap.

## Testler ve doğrulama

19 Ekim 2026 tarihinde Linux 7.2.11-1-cachyos x86_64 / glibc 2.44, CPython 3.14.8 üzerinde **20/20 geliştirme + 7/7 bağımsız test geçti**; atlanan, hata veren veya başarısız test yok. Kaynak kodu ve iki test dosyası değişmedi. Hashler ve kapsam [TESTING.md](TESTING.md) içindedir.

    python3 -B ci/run_tests.py --suite development
    python3 -B ci/run_tests.py --suite independent

Bütün testler sentetik geçici dizinleri kullanır. Windows/macOS ve Python 3.9 çalıştırılmadı; platform başarısı, sertifika veya geri yükleme garantisi iddiası yok.

## İsteğe bağlı platform workflow'u

.github/workflows/platform-tests.yml yalnız **workflow_dispatch** ile elle başlatılır; push veya pull_request tetikleyicisi yoktur. target_and_cost_verified varsayılan false'tur. Bu giriş ücret sınırı koymaz. Kota/maliyet koşulları doğrulanmadığı için bu yayın sırasında workflow tetiklenmedi.

Workflow Windows ve macOS için test hazırlığı içerir; dosyanın varlığı test sonucu değildir. Atlanan testler başarı sayılmaz; bağımsız testlerdeki POSIX varsayımları Windows'ta hata verebilir. Harness atlama/hata sayılarını açıkça raporlar. Gerçek sonuç olmadan başarı rozeti üretilmez.

Yerel .ci-results çalışma çıktıları Git'e dahil edilmez.
