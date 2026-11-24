// Person cutout mask with Apple Vision (built into macOS, nothing to install).
// The builders use it to find where the person is in a frame (so crops follow them), and the cover maker
// uses it for "pop-out" covers, where the person sits in front of the title.
//   swift person_mask.swift <in.png> <out_mask.png>
// Exit code 1 and no file when there's no person in the frame.
import Foundation
import Vision
import CoreImage
import AppKit

let args = CommandLine.arguments
guard args.count == 3 else { print("usage: swift person_mask.swift <in.png> <out_mask.png>"); exit(2) }
let inURL = URL(fileURLWithPath: args[1]), outURL = URL(fileURLWithPath: args[2])
guard let ci = CIImage(contentsOf: inURL) else { print("cannot read \(args[1])"); exit(1) }

let req = VNGeneratePersonSegmentationRequest()
req.qualityLevel = .accurate
req.outputPixelFormat = kCVPixelFormatType_OneComponent8
try VNImageRequestHandler(ciImage: ci, options: [:]).perform([req])
guard let buf = req.results?.first?.pixelBuffer else { print("no person found"); exit(1) }

// Scale the mask back up to the input size and save it as a greyscale PNG.
var mask = CIImage(cvPixelBuffer: buf)
mask = mask.transformed(by: CGAffineTransform(scaleX: ci.extent.width / mask.extent.width,
                                              y: ci.extent.height / mask.extent.height))
let ctx = CIContext()
guard let cg = ctx.createCGImage(mask, from: ci.extent) else { exit(1) }
let rep = NSBitmapImageRep(cgImage: cg)
try rep.representation(using: .png, properties: [:])!.write(to: outURL)
print(args[2])
