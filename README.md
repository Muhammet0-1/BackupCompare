# Backup Compare

Python standart kütüphanesiyle iki klasörün göreli yollarını ve dosya içeriklerini karşılaştıran, salt okunur komut satırı aracı. Dosya kopyalamaz, silmez, onarmaz; yedek oluşturmaz. Ek Python paketi veya hesap gerektirmez.

Bu sürüm, kullanıcının onayladığı özel `Muhammet0-1/BackupCompare` deposunda platform testi hazırlığı içindir. Depo testlerden sonra da private kalmalıdır. Windows/macOS desteği gerçek Actions sonuçlarıyla değerlendirilmelidir; workflow dosyasının varlığı test başarısı değildir.

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

## Testler

20 geliştirme ve 7 bağımsız test kaynakları bu taslakta değiştirilmeden korunur. Kimlikleri `ci/source_sha256.json` içindedir.

```sh
python -B ci/run_tests.py --suite development
python -B ci/run_tests.py --suite independent
```

Önceki yerel Linux/Python 3.14.8 incelemesinde 20+7 test geçti. Bu geçmiş Linux sonucu Windows/macOS başarısı değildir.

Tek workflow yalnız elle başlatılır: standart `windows-2025` ve `macos-15-intel`, x64 Python `3.9` ve `3.14`; toplam dört job. İstenen minor sürümün action tarafından bulunan tam patch sürümü çalışma raporuna yazılır. Python kurulumu bulunamazsa setup hatasıdır; test geçti sayılmaz.

Her job 8 dakika; test adımı başına 3 dakika; en fazla iki eşzamanlı job. Workflow yalnız `contents: read` izni ister, checkout kimlik bilgisini saklamaz. Paket/cache/artifact upload veya yayın adımı yoktur. Resmî checkout ve setup-python action'ları tam commit SHA ile sabittir.

Testler üretim kodunu veya eski testi uyarlayarak yeşile çevrilmez. Mevcut bağımsız suite Windows'ta POSIX'e özgü `os.geteuid()` ve dosya adlarını kullanır; hata vermesi beklenebilir. FIFO, harf duyarlılığı ve symlink yetkisi testleri de platforma bağlı atlanabilir. Gerçek sonuç elde edilmeden sayılar tahmin edilmez.

Harness tüm atlamaları nedenleriyle gösterir; atlananlar başarı sayılmaz. `PASS_WITH_SKIPS`, tam 20/20 veya 7/7 platform geçişi demek değildir. Hata/failure olan job başarısız döner. İki suite ayrı adımda çalışır; ilk suite başarısız olsa da ikinciye devam edilir. macOS geçici dizin takma yolları fiziksel yola çözülür; mevcut test/üretim dosyaları değiştirilmez.

Job summary gerçek OS/Python/runner image, commit ve source SHA256, run bağlantısı ve test sayıları içerir. Yerel `.ci-results` dosyaları commit edilmez. Gerçek Windows/macOS run olmadan ekran görüntüsü veya başarı rozeti üretilmez.

## GitHub'a gönderme ön koşulları

Onaylı hedef `Muhammet0-1/BackupCompare`, görünürlük private, dal `MS` (hesabın döndürdüğü varsayılan dal). Yüklenecek diff araç, sentetik testler, Türkçe README ve minimal CI ile sınırlıdır. Public açma/yayın yapma onayı yoktur; başka projeye eklenmez. Cuma 23 Ekim 2026 paylaşım hedefidir; zamanlama veya yayın işlemi yapılmaz.

Public repo + standart hosted runner kullanımının ücretsiz olduğu resmî belgede doğrulandı. Private hedef için hesapta kalan ücretsiz kota, uygulanacak runner maliyeti ve sıfır ücret koşulu ayrıca doğrulanmalıdır. Genel ücretsiz kota tablosu, hesabın kalan kotasının kanıtı değildir.

`target_and_cost_verified` girişi varsayılan false'tur. Bu giriş bir faturalama sınırı koymaz; doğrulamanın yerini tutmaz. Hedef/ücret koşulu çözüldükten sonra aynı workflow bir kez elle tetiklenmelidir.

Gerçek run tamamlandığında her OS/Python job'unun Summary ekranı ve test adımı sonuçları ekran görüntüsü olarak alınmalı; run URL/ID ve passed/skipped/failure/error sayılarıyla birlikte sunulmalıdır. Kimlik bilgileri veya kişisel dosyalar görüntülenmemelidir.

## Resmî kaynaklar

- [GitHub Actions ücretlendirmesi](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Standart runner etiketleri](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Workflow söz dizimi](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [checkout v6.1.0](https://github.com/actions/checkout/commit/d23441a48e516b6c34aea4fa41551a30e30af803)
- [setup-python v6.3.0](https://github.com/actions/setup-python/commit/ece7cb06caefa5fff74198d8649806c4678c61a1)

