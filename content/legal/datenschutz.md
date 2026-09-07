---
title: Datenschutzerklärung
---

Informationen nach Art. 13 DSGVO. Stand: September 2026.

**Kurzfassung:** Diese Seite untersucht das Verhalten automatisierter Clients.
Dazu wird zu jedem Aufruf ein Datensatz gespeichert, der die IP-Adresse
ausschließlich als gesalzenen Hashwert enthält — nicht im Klartext. Diese
Datensätze werden nach 180 Tagen automatisch gelöscht. Es gibt kein Tracking,
keine Cookies, keine externen Ressourcen und keine Werbung.

## 1. Verantwortlicher

dkd Internet Service GmbH
Kaiserstraße 73, 60329 Frankfurt am Main, Deutschland
E-Mail: [info@dkd.de](mailto:info@dkd.de) · Telefon: +49 69 2475218-0

## 2. Datenschutzbeauftragter

Kircher Datenschutz, Telegraphengasse 1, 36037 Fulda
[www.kircher-datenschutz.de](https://www.kircher-datenschutz.de)

## 3. Hosting und Server-Logfiles

Dieser Dienst wird bei der Mittwald CM Service GmbH & Co. KG, Königsberger
Straße 4–6, 32339 Espelkamp, betrieben. Mit dem Hoster besteht ein Vertrag zur
Auftragsverarbeitung nach Art. 28 DSGVO.

Beim Aufruf erhebt der Hoster automatisch Server-Logfiles mit IP-Adresse,
Zeitpunkt, abgerufener Ressource, Browser bzw. HTTP-Client und Referrer. Diese
Logfiles werden für maximal 14 Tage gespeichert und anschließend automatisch
gelöscht. Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO; das berechtigte
Interesse liegt in der Sicherstellung eines störungsfreien Betriebs.

## 4. Zugriffsdatensätze der Anwendung

Der Zweck dieses Dienstes ist die Untersuchung, wie sich automatisierte Clients
gegenüber den Regeln einer Website verhalten — etwa gegenüber `robots.txt` oder
gegenüber Bereichen, die ausdrücklich nicht abgerufen werden sollen. Dafür
speichert die Anwendung zu jedem Aufruf einen Datensatz mit folgenden Feldern:

- Zeitstempel des Aufrufs
- Angefragter Pfad und HTTP-Methode
- User-Agent-Zeichenkette
- Daraus abgeleitete Bot-Kennung, Bot-Name und Betreiber, sofern erkennbar
- Kennzeichen, ob ein als gesperrt markierter Pfad abgerufen wurde
- Ergebnis der Signaturprüfung nach Web Bot Auth, sofern vorhanden
- Ein Hashwert der IP-Adresse

**Zur IP-Adresse:** Die IP-Adresse wird nicht gespeichert. Gespeichert wird
ausschließlich ein mit einem geheimen Salt gebildeter SHA-256-Hashwert, gekürzt
auf 16 Zeichen. Er dient allein dazu, mehrere Aufrufe desselben Absenders als
zusammengehörig zu erkennen und deren Anzahl zu zählen. Da ein Rückschluss auf
die Adresse mit Kenntnis des Salt nicht vollständig ausgeschlossen werden kann,
behandeln wir diesen Wert als pseudonymes personenbezogenes Datum im Sinne des
Art. 4 Nr. 5 DSGVO und nicht als anonymisiert.

Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO. Das berechtigte Interesse liegt
in der Untersuchung und öffentlichen Dokumentation des Verhaltens
automatisierter Clients sowie in der Abwehr missbräuchlicher Zugriffe. Die
Verarbeitung richtet sich ihrer Natur nach an maschinelle Absender; Aufrufe
durch natürliche Personen mit einem gewöhnlichen Browser werden zwar ebenfalls
erfasst, sind für die Auswertung aber ohne Belang.

## 5. Speicherdauer

Zugriffsdatensätze werden 180 Tage nach ihrer Entstehung automatisch gelöscht.
Die Löschung läuft als wiederkehrender Vorgang im Dienst selbst und ist nicht
von einer manuellen Ausführung abhängig.

## 6. Veröffentlichung der Auswertung

Auf der Startseite wird eine Auswertung der gesammelten Daten öffentlich
dargestellt. Veröffentlicht werden ausschließlich aggregierte Werte — etwa die
Anzahl der Aufrufe je Bot und die Anzahl unterschiedlicher Absender. Die
Hashwerte selbst werden nicht veröffentlicht. Namentlich genannt werden nur
Betreiber automatisierter Clients, die sich über ihren User-Agent selbst als
solche zu erkennen geben; das sind keine personenbezogenen Angaben.

## 7. Rate Limiting

Zum Schutz vor Überlastung begrenzt der Dienst die Aufrufhäufigkeit je Absender.
Die dafür nötige IP-Adresse wird ausschließlich im Arbeitsspeicher gehalten,
nicht gespeichert und geht beim Neustart verloren. Rechtsgrundlage ist Art. 6
Abs. 1 lit. f DSGVO.

## 8. Lokale Speicherung im Browser

Die Seite speichert Ihre Auswahl zwischen heller und dunkler Darstellung im
`localStorage` Ihres Browsers unter dem Schlüssel `theme`. Dieser Wert verlässt
Ihren Rechner nicht und wird nicht an uns übertragen. Da er allein eine von
Ihnen aktiv getroffene Einstellung umsetzt, ist die Speicherung nach § 25 Abs. 2
Nr. 2 TDDDG einwilligungsfrei. Sie können ihn jederzeit über die Einstellungen
Ihres Browsers löschen.

Darüber hinaus werden keine Cookies gesetzt und keine Analyse-,
Reichweitenmessungs- oder Trackingdienste eingesetzt. Es findet keine
Profilbildung und keine automatisierte Entscheidungsfindung statt.

## 9. Schriftarten und externe Ressourcen

Alle Schriftarten und Stylesheets werden von diesem Server ausgeliefert. Es
besteht keine Verbindung zu Google Fonts oder einem anderen externen Anbieter.
Die Seiten binden keine Ressourcen von Drittservern ein.

## 10. Externe Links

Diese Seiten verlinken auf externe Websites, etwa das Quellcode-Repository bei
GitHub. Auf deren Datenverarbeitung haben wir keinen Einfluss; es gelten die
dortigen Datenschutzerklärungen. Beim Verlassen der Seite wird die
Referrer-Information nicht mitgesendet (`Referrer-Policy: no-referrer`).

## 11. Ihre Rechte

Sie haben jederzeit das Recht auf Auskunft (Art. 15 DSGVO), Berichtigung
(Art. 16), Löschung (Art. 17), Einschränkung der Verarbeitung (Art. 18),
Datenübertragbarkeit (Art. 20) und Widerspruch gegen die Verarbeitung
(Art. 21 DSGVO).

Ein Hinweis zur Auskunft: Da wir IP-Adressen nur als Hashwert speichern und
keine weiteren Identifikatoren erheben, können wir einen Datensatz einer
bestimmten Person in der Regel nicht zuordnen. Nach Art. 11 Abs. 2 DSGVO sind
wir zur Beschaffung zusätzlicher Daten allein zum Zweck der Identifizierung
nicht verpflichtet. Teilen Sie uns Ihre IP-Adresse und den ungefähren Zeitraum
mit, können wir gezielt suchen und die betreffenden Datensätze auf Wunsch
löschen.

## 12. Beschwerderecht

Sie haben das Recht, sich bei einer Datenschutz-Aufsichtsbehörde zu beschweren
(Art. 77 DSGVO). Für uns zuständig ist der Hessische Beauftragte für Datenschutz
und Informationsfreiheit, Postfach 3163, 65021 Wiesbaden,
[datenschutz.hessen.de](https://datenschutz.hessen.de).
