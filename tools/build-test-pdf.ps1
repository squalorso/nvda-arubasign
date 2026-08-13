# Builds a minimal PDF (A4, 2 pages) with 3 empty signature fields (AcroForm /Sig)
# at known positions, computing the xref table programmatically.

$out = "C:\Users\andro\Documents\addon NVDA\test\contratto_prova.pdf"
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null

function ContentStream([string]$text) {
    $s = $text
    $len = [System.Text.Encoding]::ASCII.GetByteCount($s)
    return "<< /Length $len >>`nstream`n$s`nendstream"
}

# Page 1 content: title + label near field 1
$c1 = @"
BT /F1 18 Tf 50 780 Td (CONTRATTO DI PROVA - Pagina 1) Tj ET
BT /F1 12 Tf 50 740 Td (Documento di test per addon NVDA ArubaSign.) Tj ET
BT /F1 12 Tf 350 170 Td (Firma del cliente:) Tj ET
0.8 0.8 0.8 rg 350 100 200 60 re f
"@ -replace "`r`n","`n"

# Page 2 content: labels near fields 2 and 3
$c2 = @"
BT /F1 18 Tf 50 780 Td (CONTRATTO DI PROVA - Pagina 2) Tj ET
BT /F1 12 Tf 50 470 Td (Firma per accettazione clausola 1:) Tj ET
0.8 0.8 0.8 rg 50 400 200 60 re f
BT /F1 12 Tf 350 150 Td (Firma del titolare:) Tj ET
0.8 0.8 0.8 rg 350 80 200 60 re f
"@ -replace "`r`n","`n"

$objs = @(
    # 1: Catalog
    "<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [7 0 R 8 0 R 9 0 R] /SigFlags 3 >> >>",
    # 2: Pages
    "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
    # 3: Page 1
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 10 0 R >> >> /Contents 5 0 R /Annots [7 0 R] >>",
    # 4: Page 2
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 10 0 R >> >> /Contents 6 0 R /Annots [8 0 R 9 0 R] >>",
    # 5: contents p1
    (ContentStream $c1),
    # 6: contents p2
    (ContentStream $c2),
    # 7: sig field 1 (page 1, bottom right)
    "<< /Type /Annot /Subtype /Widget /FT /Sig /T (Firma_Cliente) /Rect [350 100 550 160] /P 3 0 R /F 4 >>",
    # 8: sig field 2 (page 2, mid left)
    "<< /Type /Annot /Subtype /Widget /FT /Sig /T (Firma_Clausola_1) /Rect [50 400 250 460] /P 4 0 R /F 4 >>",
    # 9: sig field 3 (page 2, bottom right)
    "<< /Type /Annot /Subtype /Widget /FT /Sig /T (Firma_Titolare) /Rect [350 80 550 140] /P 4 0 R /F 4 >>",
    # 10: font
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
)

$sb = New-Object System.Text.StringBuilder
[void]$sb.Append("%PDF-1.6`n")
$offsets = New-Object System.Collections.Generic.List[int]
for ($i = 0; $i -lt $objs.Count; $i++) {
    $offsets.Add([System.Text.Encoding]::ASCII.GetByteCount($sb.ToString()))
    [void]$sb.Append(("{0} 0 obj`n{1}`nendobj`n" -f ($i+1), $objs[$i]))
}
$xrefPos = [System.Text.Encoding]::ASCII.GetByteCount($sb.ToString())
[void]$sb.Append("xref`n0 $($objs.Count + 1)`n")
[void]$sb.Append("0000000000 65535 f `n")
foreach ($o in $offsets) { [void]$sb.Append(("{0:D10} 00000 n `n" -f $o)) }
[void]$sb.Append("trailer`n<< /Size $($objs.Count + 1) /Root 1 0 R >>`nstartxref`n$xrefPos`n%%EOF")

[System.IO.File]::WriteAllBytes($out, [System.Text.Encoding]::ASCII.GetBytes($sb.ToString()))
Write-Output "PDF scritto: $out ($((Get-Item $out).Length) byte)"
