// Per-frame person cutout and face boxes for a video, with Apple Vision (built into macOS, no installs).
// Used by effects/core.py. Built on your Mac by effects/build_helpers.sh (setup runs it) into effects/cache/bin/track.
//
//   track <video> <faces.json>                     face box on every frame
//   track <video> <faces.json> --mask W H          also writes one W x H greyscale person mask per frame to stdout
//   track <video> <faces.json> --every N           only look at every Nth frame (quick face pass)
//
// faces.json: [[t, x, y, w, h, confidence], ...] with x, y, w, h as fractions of the frame, origin top-left.
// A frame with no face is [t]. Run it on videos ffmpeg has already turned upright (no rotation metadata).
import Foundation
import AVFoundation
import Vision
import CoreImage

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: track <video> <faces.json> [--mask W H] [--every N]\n".data(using: .utf8)!)
    exit(2)
}
var maskW = 0, maskH = 0, every = 1
var k = 3
while k < args.count {
    if args[k] == "--mask", k + 2 < args.count { maskW = Int(args[k + 1])!; maskH = Int(args[k + 2])!; k += 3 }
    else if args[k] == "--every", k + 1 < args.count { every = max(1, Int(args[k + 1])!); k += 2 }
    else { k += 1 }
}
let wantMask = maskW > 0 && maskH > 0

let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
guard let track = asset.tracks(withMediaType: .video).first else {
    FileHandle.standardError.write("no video track\n".data(using: .utf8)!); exit(1)
}
let reader = try AVAssetReader(asset: asset)
let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
    kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
output.alwaysCopiesSampleData = false
reader.add(output)
reader.startReading()

let seg = VNGeneratePersonSegmentationRequest()
seg.qualityLevel = .accurate
seg.outputPixelFormat = kCVPixelFormatType_OneComponent8
let faceReq = VNDetectFaceRectanglesRequest()
// The instance mask fills the body solidly (a shirt logo can read as "room" in the segmentation mask);
// the segmentation mask has the crisper edges. The cutout is the brighter of the two, the instance one shrunk a little.
let instReq = VNGeneratePersonInstanceMaskRequest()
let ctx = CIContext(options: [.workingColorSpace: NSNull(), .outputColorSpace: NSNull()])
var faces: [[Double]] = []
var buf = [UInt8](repeating: 0, count: max(1, maskW * maskH))
let out = FileHandle.standardOutput
var i = 0
var lastMask: Data? = nil

while let sb = output.copyNextSampleBuffer() {
    guard let pb = CMSampleBufferGetImageBuffer(sb) else { continue }
    let t = CMSampleBufferGetPresentationTimeStamp(sb).seconds
    defer { i += 1 }
    if i % every != 0 { continue }
    let handler = VNImageRequestHandler(cvPixelBuffer: pb, options: [:])
    var reqs: [VNRequest] = [faceReq]
    if wantMask { reqs.append(seg); reqs.append(instReq) }
    do { try handler.perform(reqs) } catch { }

    // the biggest face is the subject
    if let best = (faceReq.results ?? []).max(by: { $0.boundingBox.width * $0.boundingBox.height < $1.boundingBox.width * $1.boundingBox.height }) {
        let b = best.boundingBox
        faces.append([t, Double(b.minX), Double(1 - b.maxY), Double(b.width), Double(b.height), Double(best.confidence)])
    } else {
        faces.append([t])
    }

    if wantMask {
        if let mb = seg.results?.first?.pixelBuffer {
            let rect = CGRect(x: 0, y: 0, width: maskW, height: maskH)
            var m = CIImage(cvPixelBuffer: mb)
            m = m.transformed(by: CGAffineTransform(scaleX: CGFloat(maskW) / m.extent.width, y: CGFloat(maskH) / m.extent.height))
            if let r = instReq.results?.first, !r.allInstances.isEmpty,
               let ib = try? r.generateScaledMaskForImage(forInstances: r.allInstances, from: handler) {
                var im = CIImage(cvPixelBuffer: ib)
                im = im.transformed(by: CGAffineTransform(scaleX: CGFloat(maskW) / im.extent.width, y: CGFloat(maskH) / im.extent.height))
                // segmentation, but only near the instance mask (drops things it wrongly counts as the person, like a towel)
                let near = im.clampedToExtent().applyingFilter("CIMorphologyMaximum", parameters: ["inputRadius": 18]).cropped(to: rect)
                let core = im.clampedToExtent().applyingFilter("CIMorphologyMinimum", parameters: ["inputRadius": 12]).cropped(to: rect)
                m = m.applyingFilter("CIMinimumCompositing", parameters: [kCIInputBackgroundImageKey: near]).cropped(to: rect)
                m = m.applyingFilter("CIMaximumCompositing", parameters: [kCIInputBackgroundImageKey: core]).cropped(to: rect)
            }
            ctx.render(m, toBitmap: &buf, rowBytes: maskW, bounds: CGRect(x: 0, y: 0, width: maskW, height: maskH),
                       format: .L8, colorSpace: nil)
            let d = Data(buf)
            out.write(d); lastMask = d
        } else if let d = lastMask {
            out.write(d)          // no person found: hold the last mask so frames stay in step
        } else {
            out.write(Data(count: maskW * maskH))
        }
    }
}

let json = try JSONSerialization.data(withJSONObject: faces)
try json.write(to: URL(fileURLWithPath: args[2]))
FileHandle.standardError.write("track: \(i) frames, \(faces.filter { $0.count > 1 }.count) with a face\n".data(using: .utf8)!)
