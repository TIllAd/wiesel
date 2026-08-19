# eduroam / WLAN einrichten
Quelle: https://www.anleitungen.rrze.fau.de/internet-zugang/wlan/
Gecrawlt am: 2026-06-26

---

eduroam
Für Mitarbeiter und Studenten der FAU. Gäste aus anderen Einrichtungen müssen die Konfiguration ihrer Heimateinrichtung verwenden.
Auf Dienstrechnern, die von einem der IT-Betreuungszentren des RRZE betreut werden, ist die notwendige Konfiguration bereits vorhanden. Sie können sich direkt mit eduoram verbinden.
Zum Login geben Sie bitte Ihre
IdM-Benutzerkennung
gefolgt von
@fau.de
ein (z.B. ab12cdef@fau.de),
nicht
Ihre Email-Adresse. Als Passwort verwenden Sie Ihr
IdM-Passwort
, oder falls Sie die Passwortsynchronisation im IdM deaktiviert haben Ihr WLAN-Passwort.
Anleitung für Windows
Instructions for Windows
Anleitung für macOS
Instructions for macOS
Anleitung für Linux
Instructions for Linux
Anleitung für iOS
Instructions for iOS
Anleitung für Android
Instructions for Android
Für die Konfiguration des WLANs eduroam steht das Konfigurationstool eduroam CAT bereit, welches für die meisten Betriebssysteme eine automatische Konfiguration erlaubt. Es wird hierbei keine Software installiert, sondern nur ein WLAN-Profil eingerichtet. Falls nötig, wird zusätzlich ein HARICA Root-Zertifikat (von GÉANT TCS) für die Verwendung im WLAN-Profil mitinstalliert.
Hier finden Sie die Profile für die gängigen Betriebssysteme:
https://cat.eduroam.org/
Hinweise
Android-Nutzer benötigen zwingend die App
geteduroam
aus dem Google Play Store. Sie können direkt über die App das Profil herunterladen. Alternativ öffnet das Android-Profil unter obigem Link automatisch die App falls diese bereits installiert ist.
Apple-Nutzer finden bei unseren
macOS
– bzw.
iOS/iPadOS
-Anleitungen Unterstützung zur Konfiguration ihrer Geräte.
Bitte verwenden Sie für eine sichere Konfiguration ausschließlich die Profile unter obigen Links.
Eine manuelle eduroam-Konfiguration birgt große Sicherheitsrisiken und ermöglicht ggf. den Diebstahl Ihrer Benutzerdaten.
Zertifikate
Zur Nutzung des
WLAN
s ist ein
Wurzelzertifikat von HARICA
nötig
HARICA TLS RSA Root CA 2021
gültig bis 13. Februar 2045 11:55:37 MEZ
. Dieses ist im Zertifikatsspeicher der meisten gängigen Betriebssysteme vorhanden und wird andernfalls von CAT mitinstalliert. Das Wurzelzertifikat finden Sie auch unter folgendem Link:
Download des
HARICA TLS RSA Root CA 2021
Wurzelzertifikats
Viele Betriebssysteme (auch auf Mobilgeräten) fordern beim erstmaligen Verbinden den Nutzer dazu auf, trotz gültigem Zertifikat den Fingerprint des Zertifikats zu überprüfen. Dazu finden Sie hier die Fingerprints der Zertifikate der Authentifizierungsserver der FAU.
Geben Sie niemals Ihr Passwort ein, wenn Sie die Echtheit der Zertifikate nicht verifizieren können!
Fingerprints für
radius.rrze.uni-erlangen.de
(FAU-Event, gültig bis 30. Januar 2027 14:17:49 MEZ, augestellt von GEANT TLS RSA 1):
sha1: 0E:39:08:49:2F:74:06:B9:48:7A:43:8D:25:8C:CF:D0:A9:A4:28:4C
sha256: 76:91:5B:12:68:C1:23:11:A1:0B:30:F6:33:AE:AB:58:7C:B1:D2:38:68:DB:4A:81:9F:76:62:84:BD:A1:83:27
Fingerprints für
eradius.rrze.de
(eduroam, gültig bis 2. März 2027 13:48:08 MEZ, augestellt von GEANT TLS RSA 1):
sha1: 36:BB:50:4A:20:DF:51:99:1C:35:AC:6D:14:CD:2B:CB:C2:38:AD:B2
sha256: E9:72:49:B5:C9:60:45:42:9E:CF:C3:86:19:ED:59:7E:A5:C9:02:E3:6F:56:28:0C:0F:2E:D5:AE:2B:7A:F8:E9
QR-Code für eduroam
Eduroam Konfigurationsprofile: https://cat.eduroam.org/
Download des
HARICA TLS RSA Root CA 2021
Wurzelzertifikats
FAU-Event
Für Gastwissenschaftler, -dozenten oder Entsandte Personen mit ihrer IdM-Kennung oder für Gäste über separate Kongresskennungen.
Hier finden Sie Anleitungen und Konfigurationsprofile für die Einrichtung des WLANs unter den gängigen Betriebssystemen:
Anleitung für Windows 11
Anleitung für Linux
Anleitung für Android 11 ff.
Konfigurationsprofile für iOS, iPadOS
und
macOS
