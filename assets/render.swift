// Preview renderer for previews.py: one file in, one sRGB JPEG out, a JSON line on stdout.
//
//   render <input> <output.jpg> <max px> [pdf|image|nsimage]
//
// pdf      CoreGraphics PDF (also Illustrator files saved PDF-compatible): page 1, page count, size in points
// image    ImageIO: JPEG, HEIC, PNG, GIF, WebP, TIFF, PSD/PSB, camera raw ... EXIF orientation applied,
//          pixel size of the original, EXIF capture date
// nsimage  AppKit NSImage (SVG and anything else AppKit can draw)
// Transparency is flattened onto light grey. previews.py compiles it once (swiftc, from the Xcode Command
// Line Tools) into <asset cache>/bin/render, and falls back to Pillow and sips when swiftc isn't there.
import AppKit
import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count >= 4, let maxPx = Double(args[3]) else {
    FileHandle.standardError.write("usage: render <in> <out.jpg> <max px> [pdf|image|nsimage]\n".data(using: .utf8)!)
    exit(2)
}
let inURL = URL(fileURLWithPath: args[1])
let outURL = URL(fileURLWithPath: args[2])
let mode = args.count > 4 ? args[4] : "image"
let srgb = CGColorSpace(name: CGColorSpace.sRGB)!
var info: [String: Any] = [:]

func fail(_ msg: String) -> Never {
    let d = try! JSONSerialization.data(withJSONObject: ["error": msg])
    print(String(data: d, encoding: .utf8)!)
    exit(1)
}

func canvas(_ w: Int, _ h: Int) -> CGContext {
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: srgb,
                        bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.setFillColor(CGColor(srgbRed: 0.88, green: 0.88, blue: 0.88, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.interpolationQuality = .high
    return ctx
}

func fit(_ w: Double, _ h: Double) -> (Int, Int) {
    let s = min(1.0, maxPx / max(w, h))
    return (max(1, Int((w * s).rounded())), max(1, Int((h * s).rounded())))
}

func save(_ img: CGImage) {
    guard let dest = CGImageDestinationCreateWithURL(outURL as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else { fail("cannot write output") }
    CGImageDestinationAddImage(dest, img, [kCGImageDestinationLossyCompressionQuality: 0.8] as CFDictionary)
    if !CGImageDestinationFinalize(dest) { fail("cannot write output") }
}

func flatten(_ img: CGImage, _ w: Int, _ h: Int) -> CGImage {
    let ctx = canvas(w, h)
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    return ctx.makeImage()!
}

switch mode {
case "pdf":
    guard let doc = CGPDFDocument(inURL as CFURL) else { fail("not a readable PDF") }
    if doc.isEncrypted && !doc.unlockWithPassword("") { fail("encrypted PDF") }
    guard doc.numberOfPages > 0, let page = doc.page(at: 1) else { fail("PDF has no pages") }
    var box = page.getBoxRect(.cropBox)
    let rot = ((page.rotationAngle % 360) + 360) % 360
    if rot == 90 || rot == 270 { box = CGRect(x: 0, y: 0, width: box.height, height: box.width) }
    guard box.width > 0, box.height > 0 else { fail("PDF page has no size") }
    let (w, h) = fit(Double(box.width), Double(box.height))
    let ctx = canvas(w, h)
    ctx.setFillColor(CGColor(srgbRed: 1, green: 1, blue: 1, alpha: 1))   // paper stays white
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.concatenate(page.getDrawingTransform(.cropBox, rect: CGRect(x: 0, y: 0, width: w, height: h), rotate: 0, preserveAspectRatio: true))
    ctx.drawPDFPage(page)
    save(ctx.makeImage()!)
    info = ["width": Int(box.width.rounded()), "height": Int(box.height.rounded()), "pages": doc.numberOfPages, "units": "pt"]

case "nsimage":
    guard let ns = NSImage(contentsOf: inURL), ns.size.width > 0, ns.size.height > 0 else { fail("AppKit cannot open it") }
    var pw = Double(ns.size.width), ph = Double(ns.size.height)
    if let rep = ns.representations.first, rep.pixelsWide > 0, rep.pixelsHigh > 0 { pw = Double(rep.pixelsWide); ph = Double(rep.pixelsHigh) }
    let (w, h) = fit(pw, ph)
    let ctx = canvas(w, h)
    let g = NSGraphicsContext(cgContext: ctx, flipped: false)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = g
    ns.draw(in: NSRect(x: 0, y: 0, width: w, height: h))
    NSGraphicsContext.restoreGraphicsState()
    save(ctx.makeImage()!)
    info = ["width": Int(pw.rounded()), "height": Int(ph.rounded())]

default:
    guard let src = CGImageSourceCreateWithURL(inURL as CFURL, [kCGImageSourceShouldCache: false] as CFDictionary),
          CGImageSourceGetCount(src) > 0 else { fail("ImageIO cannot open it") }
    let props = (CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any]) ?? [:]
    var pw = (props[kCGImagePropertyPixelWidth] as? Int) ?? 0
    var ph = (props[kCGImagePropertyPixelHeight] as? Int) ?? 0
    let orient = (props[kCGImagePropertyOrientation] as? Int) ?? 1
    if orient >= 5 && orient <= 8 { swap(&pw, &ph) }
    let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any]
    if let t = (exif?[kCGImagePropertyExifDateTimeOriginal] as? String) ?? (exif?[kCGImagePropertyExifDateTimeDigitized] as? String) {
        info["taken"] = t
    }
    let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                 kCGImageSourceCreateThumbnailWithTransform: true,
                                 kCGImageSourceThumbnailMaxPixelSize: Int(maxPx),
                                 kCGImageSourceShouldCacheImmediately: true]
    guard let thumb = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { fail("ImageIO cannot decode it") }
    let (w, h) = fit(Double(thumb.width), Double(thumb.height))
    save(flatten(thumb, w, h))
    if pw == 0 || ph == 0 { pw = thumb.width; ph = thumb.height }
    info["width"] = pw
    info["height"] = ph
    if CGImageSourceGetCount(src) > 1, let t = CGImageSourceGetType(src) as String?, t != "public.heic", t != "public.heif" {
        info["frames"] = CGImageSourceGetCount(src)
    }
}

let d = try! JSONSerialization.data(withJSONObject: info)
print(String(data: d, encoding: .utf8)!)
