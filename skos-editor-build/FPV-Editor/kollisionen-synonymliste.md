# Kollisionen in der Synonymliste (Stand der hochgeladenen fpv.ttl)

Erzeugt mit denselben Regeln wie der Editor (und `ttl2jsonl.py`): Konzepte mit `useInSynonymList true`, Blacklist und Mindestgröße 2 berücksichtigt, Groß-/Kleinschreibung ignoriert. **23 Konzeptpaarungen**, beteiligt sind **45 Konzepte**.

Auflösung je Zeile: die gemeinsame Benennung bei allen bis auf ein Konzept entfernen, oder bei einem Konzept den Haken „In Synonymliste verwenden“ wegnehmen. Bei „Benennungen identisch“ ist zu prüfen, ob es sich um ein doppelt angelegtes Konzept handelt. Hinweis: Ein Konzept bekommt erst ab zwei verwertbaren Benennungen ein Synonymset; bleibt nach dem Entfernen nur die Vorzugsbenennung übrig, entfällt sein Set ohnehin.

| Gruppe | Anzahl |
|---|---|
| gleiche Benennung, unterschiedliche Langformen | 16 |
| nur Groß-/Kleinschreibung | 4 |
| Benennungen identisch (mögliche Doppelanlage) | 3 |

| Gemeinsame Benennung(en) | Konzepte (Kennung — Vorzugsbenennung) | Einordnung |
|---|---|---|
| „CDS“ / „Centre des démocrates sociaux“ | `ex:CDS` — Centre des démocrates sociaux<br>`ex:CentreDS` — Centre des démocrates sociaux | Benennungen identisch (mögliche Doppelanlage) |
| „Deutsche Parlamentarische Gesellschaft“ | `ex:DParlG` — Deutsche Parlamentarische Gesellschaft<br>`ex:DPG` — Deutsche Parlamentarische Gesellschaft | Benennungen identisch (mögliche Doppelanlage) |
| „PVAP“ / „PZPR“ / „Polnische Vereinigte Arbeiterpartei“ / „Polska Zjednoczona Partia Robotnicza“ | `ex:PVAP` — Polska Zjednoczona Partia Robotnicza<br>`ex:PZPR` — Polska Zjednoczona Partia Robotnicza | Benennungen identisch (mögliche Doppelanlage) |
| „ASF“ | `ex:ASF` — Aktion Sühnezeichen Friedensdienste<br>`ex:AsozF` — Arbeitsgemeinschaft Sozialdemokratischer Frauen | gleiche Benennung, unterschiedliche Langformen |
| „DBB“ | `ex:BBk` — Deutsche Bundesbank<br>`ex:DBB` — Deutscher Beamtenbund | gleiche Benennung, unterschiedliche Langformen |
| „BfA“ | `ex:BfA` — Bundesversicherungsanstalt für Angestellte<br>`ex:BfArbeit` — Bundesanstalt für Arbeit | gleiche Benennung, unterschiedliche Langformen |
| „BMA“ | `ex:BMA` — Bundesministerium für Arbeit<br>`ex:BMAS` — Bundesministerium für Arbeit und Sozialordnung | gleiche Benennung, unterschiedliche Langformen |
| „BMG“ | `ex:BMG` — Bundesministerium für gesamtdeutsche Fragen<br>`ex:BMGes` — Bundesministerium für Gesundheitswesen | gleiche Benennung, unterschiedliche Langformen |
| „CDA“ | `ex:CDA` — Christlich-Demokratische Arbeitnehmerschaft Deutschlands<br>`ex:CDApp` — Christen-Democratisch Appèl | gleiche Benennung, unterschiedliche Langformen |
| „CVP“ | `ex:CVP-BE` — Christelijke Volkspartij<br>`ex:CVP-SL` — Christliche Volkspartei des Saarlandes | gleiche Benennung, unterschiedliche Langformen |
| „DBV“ | `ex:DBV` — Deutscher Bund für Vogelschutz<br>`ex:DtBauernV` — Deutscher Bauernverband | gleiche Benennung, unterschiedliche Langformen |
| „DGK“ | `ex:DeuGK` — Deutsches Grünes Kreuz<br>`ex:DGK` — Deutsche Genossenschaftskasse | gleiche Benennung, unterschiedliche Langformen |
| „DPG“ | `ex:DParlG` — Deutsche Parlamentarische Gesellschaft<br>`ex:DPG` — Deutsche Parlamentarische Gesellschaft<br>`ex:DPGe` — Deutsche Postgewerkschaft | gleiche Benennung, unterschiedliche Langformen |
| „DRP“ | `ex:DR` — Deutsche Rechtspartei<br>`ex:DRP` — Deutsche Reichspartei | gleiche Benennung, unterschiedliche Langformen |
| „DVP“ | `ex:DV` — Deutsche Volkspartei<br>`ex:DVP` — Demokratische Volkspartei | gleiche Benennung, unterschiedliche Langformen |
| „DWK“ | `ex:DWK` — Deutsche Wirtschaftskommission<br>`ex:DWKern` — Deutsche Gesellschaft für Wiederaufarbeitung von Kernbrennstoffen | gleiche Benennung, unterschiedliche Langformen |
| „DZP“ | `ex:DZP` — Deutsche Zentrumspartei<br>`ex:DZPFraktBT` — Bundestagsfraktion der Deutschen Zentrumspartei | gleiche Benennung, unterschiedliche Langformen |
| „Helaba“ | `ex:Helaba` — Hessische Landesbank<br>`ex:HelabaThue` — Landesbank Hessen-Thüringen | gleiche Benennung, unterschiedliche Langformen |
| „NRZ“ | `ex:NRhZ` — Neue Rhein-Zeitung<br>`ex:NRZ` — Neue Ruhr-Zeitung | gleiche Benennung, unterschiedliche Langformen |
| „MoPo“ / „Mopo“ | `ex:BerMoPo` — Berliner Morgenpost<br>`ex:MopoHH` — Hamburger Morgenpost | nur Groß-/Kleinschreibung |
| „DDP“ / „ddp“ | `ex:DDP` — Deutsche Demokratische Partei<br>`ex:ddp` — Deutscher Depeschendienst | nur Groß-/Kleinschreibung |
| „DKP“ / „DkP“ | `ex:DKP` — Deutsche Kommunistische Partei<br>`ex:DkP` — Deutschkonservative Partei | nur Groß-/Kleinschreibung |
| „GDP“ / „GdP“ | `ex:GDP` — Gesamtdeutsche Partei<br>`ex:GdPol` — Gewerkschaft der Polizei | nur Groß-/Kleinschreibung |
