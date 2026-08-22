# -*- coding: UTF-8 -*-
# ArubaSign - Campi firma
# Addon NVDA per rilevare i campi firma nella vista "Firma grafica" di ArubaSign
# e apporvi la firma grafica con un clic simulato, senza usare il mouse.
#
# Copyright (C) 2026 Alexandru Vida
# Rilasciato sotto GNU General Public License v2.
#
# Come funziona:
# ArubaSign (dalla versione 24 circa) disegna la propria interfaccia in HTML
# dentro un controllo WebView2 (Chromium). Nella vista di posizionamento della
# firma grafica, ogni campo firma del PDF viene esposto nell'albero
# UI Automation come elemento con AutomationId "PDFSignatureAnnotation_<nome>"
# e classe "pdf_signature_annotation", completo di rettangolo sullo schermo.
# L'addon enumera questi elementi, li porta in vista con ScrollItemPattern
# (ArubaSign cambia pagina da solo) e simula un clic sinistro al centro del
# rettangolo: ArubaSign appone la firma grafica in quel punto senza ulteriori
# conferme.

import ctypes
import re

import wx

import api
import appModuleHandler
import globalCommands
import globalPluginHandler
import gui
import mouseHandler
import scriptHandler
import tones
import ui
import UIAHandler
import winUser
from logHandler import log
from scriptHandler import script

try:
	UIA = UIAHandler.UIA  # NVDA moderni: modulo comtypes.gen.UIAutomationClient
except AttributeError:
	import comtypes.gen.UIAutomationClient as UIA

# Costanti UI Automation (valori definiti da Windows, stabili)
UIA_AutomationIdPropertyId = 30011
UIA_ClassNamePropertyId = 30012
UIA_InvokePatternId = 10000
UIA_ScrollItemPatternId = 10017
TreeScope_Descendants = 4

ANNOTATION_PREFIX = "PDFSignatureAnnotation_"
ANNOTATION_CLASS = "pdf_signature_annotation"
PROSEGUI_BUTTON_ID = "pdfView_footer_continue_button"
SIGN_LAYER_RE = re.compile(r"page_(\d+)_signLayer")
ARUBASIGN_EXE = "arubasign64.exe"
# Attese (in millisecondi) fra scorrimento e clic: il viewer anima lo scroll.
SCROLL_TO_CLICK_DELAY = 600
BETWEEN_FIELDS_DELAY = 800

user32 = ctypes.windll.user32
# Firme esplicite: con NVDA a 64 bit (2026.1+) gli handle di finestra sono
# puntatori a 64 bit e non vanno lasciati al default ctypes (int a 32 bit).
user32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.EnumWindows.restype = ctypes.c_bool
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.restype = ctypes.c_bool


class CampoFirma(object):
	"""Un campo firma rilevato nella vista di ArubaSign."""

	def __init__(self, element, automationId, page, top, left):
		self.element = element
		self.automationId = automationId
		# Nome leggibile: la parte dopo il prefisso, con underscore resi come spazi.
		self.nome = automationId[len(ANNOTATION_PREFIX):].replace("_", " ").strip() or automationId
		self.page = page
		self.top = top
		self.left = left

	def etichetta(self, firmato):
		# Etichetta mostrata nell'elenco della finestra di dialogo.
		testo = "{nome}, pagina {pagina}".format(nome=self.nome, pagina=self.page)
		if firmato:
			testo += " (firmato in questa sessione)"
		return testo


def _trovaFinestraArubaSign():
	"""Restituisce l'handle della finestra principale di ArubaSign, o None."""
	risultato = []

	@ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
	def callback(hwnd, lParam):
		if not user32.IsWindowVisible(hwnd):
			return True
		pid = ctypes.c_ulong()
		user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
		try:
			appName = appModuleHandler.getAppNameFromProcessID(pid.value, True)
		except Exception:
			return True
		if appName and appName.lower() == ARUBASIGN_EXE:
			buf = ctypes.create_unicode_buffer(256)
			user32.GetClassNameW(hwnd, buf, 256)
			if buf.value.startswith("SWT_Window"):
				risultato.append(hwnd)
				return False
		return True

	user32.EnumWindows(ctypes.cast(callback, ctypes.c_void_p), None)
	return risultato[0] if risultato else None


class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	scriptCategory = "ArubaSign - Campi firma"

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		# AutomationId dei campi firmati in questa sessione, con una chiave che
		# identifica il documento corrente per azzerare lo stato quando cambia.
		self._firmati = set()
		self._chiaveDocumento = None
		self._dialogo = None
		self._timer = None

	def terminate(self):
		if self._timer:
			self._timer.Stop()
		super(GlobalPlugin, self).terminate()

	# ------------------------------------------------------------------
	# Ricerca degli elementi via UI Automation

	def _radiceArubaSign(self):
		hwnd = _trovaFinestraArubaSign()
		if not hwnd:
			return None, None
		try:
			radice = UIAHandler.handler.clientObject.ElementFromHandle(hwnd)
		except Exception:
			log.debugWarning("ElementFromHandle fallita per ArubaSign", exc_info=True)
			return None, None
		return hwnd, radice

	def _trovaCampi(self, radice):
		"""Restituisce la lista dei CampoFirma presenti nella vista corrente."""
		client = UIAHandler.handler.clientObject
		condizione = client.CreatePropertyCondition(UIA_ClassNamePropertyId, ANNOTATION_CLASS)
		try:
			trovati = radice.FindAll(TreeScope_Descendants, condizione)
		except Exception:
			log.debugWarning("FindAll delle annotazioni firma fallita", exc_info=True)
			return []
		campi = []
		walker = client.RawViewWalker
		for i in range(trovati.Length):
			el = trovati.GetElement(i)
			try:
				automationId = el.CurrentAutomationId
			except Exception:
				continue
			if not automationId.startswith(ANNOTATION_PREFIX):
				continue
			pagina = self._paginaDiElemento(walker, el)
			try:
				rett = el.CurrentBoundingRectangle
				top, left = rett.top, rett.left
			except Exception:
				top, left = 0, 0
			campi.append(CampoFirma(el, automationId, pagina, top, left))
		campi.sort(key=lambda c: (c.page, c.top, c.left))
		return campi

	def _paginaDiElemento(self, walker, el):
		"""Risale i genitori fino a page_<n>_signLayer e restituisce n+1."""
		corrente = el
		for _ in range(6):
			try:
				corrente = walker.GetParentElement(corrente)
				if not corrente:
					break
				match = SIGN_LAYER_RE.match(corrente.CurrentAutomationId or "")
				if match:
					return int(match.group(1)) + 1
			except Exception:
				break
		return 0

	def _trovaPulsanteProsegui(self, radice):
		client = UIAHandler.handler.clientObject
		condizione = client.CreatePropertyCondition(UIA_AutomationIdPropertyId, PROSEGUI_BUTTON_ID)
		try:
			return radice.FindFirst(TreeScope_Descendants, condizione)
		except Exception:
			return None

	# ------------------------------------------------------------------
	# Azioni sui campi

	def _portaInPrimoPiano(self, hwnd):
		try:
			winUser.setForegroundWindow(hwnd)
		except Exception:
			user32.SetForegroundWindow(hwnd)

	def _scorriAlCampo(self, campo):
		punk = campo.element.GetCurrentPattern(UIA_ScrollItemPatternId)
		pattern = punk.QueryInterface(UIA.IUIAutomationScrollItemPattern)
		pattern.ScrollIntoView()

	def _cliccaCampo(self, campo):
		rett = campo.element.CurrentBoundingRectangle
		x = int((rett.left + rett.right) / 2)
		y = int((rett.top + rett.bottom) / 2)
		winUser.setCursorPos(x, y)
		mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTDOWN, 0, 0)
		mouseHandler.executeMouseEvent(winUser.MOUSEEVENTF_LEFTUP, 0, 0)
		self._firmati.add(campo.automationId)
		tones.beep(880, 60)

	def firmaCampo(self, hwnd, campo, alTermine=None):
		"""Porta il campo in vista e ci clicca sopra. Asincrono (timer wx)."""
		self._portaInPrimoPiano(hwnd)
		try:
			self._scorriAlCampo(campo)
		except Exception:
			log.error("ScrollIntoView fallita per %s" % campo.automationId, exc_info=True)
			ui.message("Impossibile raggiungere il campo {0}.".format(campo.nome))
			return

		def dopoScroll():
			try:
				self._cliccaCampo(campo)
			except Exception:
				log.error("Clic fallito per %s" % campo.automationId, exc_info=True)
				ui.message("Impossibile cliccare sul campo {0}.".format(campo.nome))
				return
			if alTermine:
				alTermine()
			else:
				ui.message(
					"Firma apposta su {nome}, pagina {pagina}.".format(nome=campo.nome, pagina=campo.page)
				)

		self._timer = wx.CallLater(SCROLL_TO_CLICK_DELAY, dopoScroll)

	def firmaTutti(self, hwnd, campi):
		"""Firma in sequenza tutti i campi non ancora firmati in sessione."""
		coda = [c for c in campi if c.automationId not in self._firmati]
		if not coda:
			ui.message("Nessun campo da firmare: risultano già tutti firmati in questa sessione.")
			return
		totale = len(coda)
		ui.message("Apposizione della firma su {0} campi. Attendi.".format(totale))

		def passo():
			if not coda:
				ui.message(
					"Fatto: firma apposta su {0} campi. "
					"Ora puoi attivare il pulsante Prosegui di ArubaSign.".format(totale)
				)
				return
			campo = coda.pop(0)
			self.firmaCampo(
				hwnd,
				campo,
				alTermine=lambda: self._prossimoPasso(passo),
			)

		passo()

	def _prossimoPasso(self, passo):
		self._timer = wx.CallLater(BETWEEN_FIELDS_DELAY, passo)

	def attivaProsegui(self, radice):
		pulsante = self._trovaPulsanteProsegui(radice)
		if not pulsante:
			ui.message("Pulsante Prosegui non trovato.")
			return
		try:
			classe = pulsante.CurrentClassName or ""
		except Exception:
			classe = ""
		if "disabled" in classe:
			ui.message("Il pulsante Prosegui è disattivato: apponi prima almeno una firma.")
			return
		try:
			punk = pulsante.GetCurrentPattern(UIA_InvokePatternId)
			punk.QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
			ui.message("Prosegui attivato. Continua con la procedura di firma di ArubaSign.")
		except Exception:
			log.error("Invoke di Prosegui fallita", exc_info=True)
			ui.message("Impossibile attivare il pulsante Prosegui.")

	# ------------------------------------------------------------------
	# Script principale

	@script(
		description=(
			"Apre l'elenco dei campi firma del documento nella vista Firma grafica di ArubaSign. "
			"Fuori da ArubaSign esegue la normale funzione di NVDA associata al gesto "
			"(modalità riposo nel layout desktop, lettura della selezione nel layout laptop)."
		),
		# Oltre alla forma normalizzata si registra esplicitamente la variante
		# con blocco maiuscole, per gli utenti che usano CapsLock come tasto NVDA.
		gestures=("kb:NVDA+shift+s", "kb:capslock+shift+s"),
	)
	def script_elencoCampiFirma(self, gesture):
		primoPiano = api.getForegroundObject()
		appName = ""
		try:
			appName = primoPiano.appModule.appName.lower()
		except Exception:
			pass
		if not appName.startswith("arubasign"):
			# Non siamo in ArubaSign: esegue la funzione che NVDA assegna di suo
			# a questo gesto nel layout tastiera in uso (desktop: modalità
			# riposo; laptop: lettura della selezione corrente).
			originale = None
			try:
				originale = globalCommands.commands.getScript(gesture)
			except Exception:
				pass
			if originale:
				scriptHandler.executeScript(originale, gesture)
			else:
				globalCommands.commands.script_toggleCurrentAppSleepMode(gesture)
			return

		hwnd, radice = self._radiceArubaSign()
		if not radice:
			ui.message("Finestra di ArubaSign non trovata.")
			return
		campi = self._trovaCampi(radice)
		if not campi:
			ui.message(
				"Nessun campo firma rilevato. Questo comando funziona nella schermata "
				"di posizionamento della firma grafica: carica un documento, verifica "
				"che la casella Firma Grafica sia attivata e premi Prosegui e firma. "
				"Se il documento non contiene campi firma predisposti, i campi non compaiono."
			)
			return

		# Azzera lo stato "firmato" se il documento è cambiato.
		chiave = (hwnd, tuple(sorted(c.automationId for c in campi)))
		if chiave != self._chiaveDocumento:
			self._chiaveDocumento = chiave
			self._firmati.clear()

		if self._dialogo:
			try:
				self._dialogo.Destroy()
			except Exception:
				pass
			self._dialogo = None
		self._dialogo = DialogoCampiFirma(self, hwnd, radice, campi)
		gui.mainFrame.prePopup()
		self._dialogo.Show()
		self._dialogo.Raise()
		gui.mainFrame.postPopup()


class DialogoCampiFirma(wx.Dialog):
	"""Finestra con l'elenco dei campi firma e i pulsanti di azione."""

	def __init__(self, plugin, hwnd, radice, campi):
		super(DialogoCampiFirma, self).__init__(
			gui.mainFrame, title="Campi firma del documento - ArubaSign"
		)
		self.plugin = plugin
		self.hwnd = hwnd
		self.radice = radice
		self.campi = campi

		sizer = wx.BoxSizer(wx.VERTICAL)
		etichetta = wx.StaticText(
			self, label="Campi firma trovati: {0}. Invio per firmare il campo selezionato.".format(len(campi))
		)
		sizer.Add(etichetta, flag=wx.ALL, border=8)
		self.lista = wx.ListBox(self, choices=self._etichette(), size=(480, 200))
		if self.lista.GetCount():
			self.lista.SetSelection(0)
		sizer.Add(self.lista, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

		pulsanti = wx.BoxSizer(wx.HORIZONTAL)
		self.btnFirma = wx.Button(self, label="&Firma campo selezionato")
		self.btnTutti = wx.Button(self, label="Firma &tutti i campi")
		self.btnProsegui = wx.Button(self, label="Attiva &Prosegui")
		self.btnChiudi = wx.Button(self, wx.ID_CANCEL, label="&Chiudi")
		for b in (self.btnFirma, self.btnTutti, self.btnProsegui, self.btnChiudi):
			pulsanti.Add(b, flag=wx.ALL, border=4)
		sizer.Add(pulsanti, flag=wx.ALIGN_CENTER)

		self.SetSizerAndFit(sizer)
		self.btnFirma.SetDefault()

		self.btnFirma.Bind(wx.EVT_BUTTON, self.onFirma)
		self.btnTutti.Bind(wx.EVT_BUTTON, self.onFirmaTutti)
		self.btnProsegui.Bind(wx.EVT_BUTTON, self.onProsegui)
		self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self.onFirma)
		self.Bind(wx.EVT_CHAR_HOOK, self.onTasto)
		self.Bind(wx.EVT_CLOSE, self.onChiudi)
		self.btnChiudi.Bind(wx.EVT_BUTTON, self.onChiudi)

		self.lista.SetFocus()
		self.CentreOnScreen()

	def _etichette(self):
		return [c.etichetta(c.automationId in self.plugin._firmati) for c in self.campi]

	def onTasto(self, evento):
		codice = evento.GetKeyCode()
		if codice == wx.WXK_RETURN and self.FindFocus() is self.lista:
			self.onFirma(None)
		elif codice == wx.WXK_ESCAPE:
			self.onChiudi(None)
		else:
			evento.Skip()

	def _chiudiEd(self, azione):
		# Chiude la finestra e poi esegue l'azione, così il clic simulato
		# avviene con ArubaSign in primo piano.
		self.Hide()
		self.Destroy()
		self.plugin._dialogo = None
		wx.CallAfter(azione)

	def onFirma(self, evento):
		indice = self.lista.GetSelection()
		if indice == wx.NOT_FOUND:
			ui.message("Seleziona prima un campo dall'elenco.")
			return
		campo = self.campi[indice]
		self._chiudiEd(lambda: self.plugin.firmaCampo(self.hwnd, campo))

	def onFirmaTutti(self, evento):
		self._chiudiEd(lambda: self.plugin.firmaTutti(self.hwnd, self.campi))

	def onProsegui(self, evento):
		self._chiudiEd(lambda: self.plugin.attivaProsegui(self.radice))

	def onChiudi(self, evento):
		self.Hide()
		self.Destroy()
		self.plugin._dialogo = None
