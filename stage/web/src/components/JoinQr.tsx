import qrcode from 'qrcode-generator'
import { useMemo } from 'react'

/**
 * A QR code for this page's address, so a phone can join from the table screen.
 * A phone cannot reach "localhost": then the screen says to open the page by the host's network address.
 */
export function JoinQr() {
  const url = `${location.origin}/`
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)
  const svg = useMemo(() => {
    const qr = qrcode(0, 'M')
    qr.addData(url)
    qr.make()
    return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true })
  }, [url])
  return (
    <section className="flex flex-col gap-2 border-2 border-[var(--border)] p-2">
      <h2 className="pixel-font text-[10px] text-[var(--gold)]">Join</h2>
      {local ? (
        <p className="text-sm text-[var(--dim)]">
          This page uses the address <b>{location.host}</b>. A phone cannot open it. Open this page by the server's network address, and a code appears here.
        </p>
      ) : (
        <>
          <div className="mx-auto w-32 bg-white p-1" dangerouslySetInnerHTML={{ __html: svg }} aria-label={`QR code for ${url}`} role="img" />
          <p className="break-all text-center text-sm">{url}</p>
        </>
      )}
    </section>
  )
}
