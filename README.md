# ArubaSign - Campi firma (addon per NVDA)

Addon per lo screen reader [NVDA](https://www.nvaccess.org/) che rende accessibile
l'apposizione della **firma grafica** in [ArubaSign](https://www.pec.it/scarica-software-firma-digitale.aspx),
il client di firma digitale di Aruba.

## Il problema

Nella vista «Firma grafica» di ArubaSign il documento è mostrato come immagine:
con lo screen reader non è possibile sapere dove si trovano i campi firma, e
l'OCR arriva al massimo vicino all'etichetta di testo, mai dentro il campo.
Molti utenti non vedenti ripiegano quindi sulla firma invisibile.

## La soluzione

ArubaSign espone internamente (tramite UI Automation, nell'interfaccia WebView2)
ogni campo firma del documento come elemento `PDFSignatureAnnotation_<nome>` con
il rettangolo esatto sullo schermo, per tutte le pagine. Questo addon:

1. enumera quei campi (nome e pagina) e li presenta in un elenco accessibile;
2. alla pressione di Invio porta il campo in vista (ArubaSign cambia pagina da
   solo) e simula un clic al centro del campo: la firma grafica viene apposta
   esattamente lì, senza ulteriori conferme;
3. con «Firma tutti i campi» ripete l'operazione su ogni campo del documento —
   utile per i contratti con una firma per ogni clausola.

## Uso

1. In ArubaSign carica il documento, verifica che «Firma Grafica» sia attivata
   e attiva «Prosegui e firma» per aprire la schermata di posizionamento.
2. Premi **NVDA+Shift+S**: si apre l'elenco dei campi firma.
3. Invio sul campo per firmarlo, oppure «Firma tutti i campi», poi
   «Attiva Prosegui» per continuare con la normale procedura di firma
   (credenziali e OTP per la firma remota — l'addon non tocca mai le credenziali).

L'addon è un app module: il comando NVDA+Shift+S esiste solo dentro
ArubaSign, e fuori dall'applicazione NVDA si comporta esattamente come se
l'addon non ci fosse. Il gesto è personalizzabile da Preferenze → Gesti di
immissione, categoria «ArubaSign - Campi firma» (con ArubaSign in primo
piano).

## Installazione

Scarica il file `arubaSignCampiFirma-<versione>.nvda-addon` dalle
[release](https://github.com/squalorso/nvda-arubasign/releases) e
aprilo con Invio: NVDA proporrà l'installazione. In alternativa, compila il
pacchetto dal sorgente (sotto).

## Compilazione dal sorgente

Serve solo PowerShell (Windows):

```powershell
.\build.ps1
```

Il pacchetto viene creato in `dist\`.

## Struttura del progetto

- `addon\manifest.ini` — metadati dell'addon
- `addon\appModules\arubasign64.py` — tutto il codice (app module: attivo solo dentro ArubaSign)
- `addon\doc\it\readme.html` — guida mostrata dal gestore componenti di NVDA
- `test\contratto_prova.pdf` — PDF di prova con 3 campi firma (2 pagine)
- `tools\build-test-pdf.ps1` — script che rigenera il PDF di prova
- `build.ps1` — crea il pacchetto `.nvda-addon`

## Compatibilità

- ArubaSign 24.1.1 (interfaccia WebView2); versioni precedenti con la vecchia
  interfaccia SWT nativa non sono supportate.
- NVDA 2026.1 o successiva. Il requisito riflette ciò che è realmente provato:
  la risoluzione dell'app dentro WebView2 esiste da NVDA 2024.3, ma le versioni
  precedenti alla 2026.1 non sono verificate e non vengono dichiarate.

## Licenza

GNU General Public License v2, come NVDA. Vedi [LICENSE](LICENSE).
