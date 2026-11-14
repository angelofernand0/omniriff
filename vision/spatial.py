"""Expressive 3D spatial gesture controller with StrumGuard and DualAxis control.

Runs independently as `python -m vision.spatial` without touching vision/control.py
or vision/__main__.py, respecting team ownership and file boundaries.
"""
import argparse
import json
import math
from pathlib import Path
import socket
import time

from .expressive import DualAxisController, compute_hand_orientation
from .hand_view import HandView
from .stage import StageHUD
from .tracking import HandSelector
from .zones import Rect, StrumGuard


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True, help='MediaPipe hand_landmarker.task model path')
    p.add_argument('--video', help='Recorded video; otherwise use webcam')
    p.add_argument('--camera', type=int, default=0)
    p.add_argument('--max-hand-jump', type=float, default=0.30,
                   help='maximum normalized wrist movement per frame before tracking fails closed')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=47800)
    p.add_argument('--pair-rate', type=float, default=10.0,
                   help='pairs per second (max 15.0 to guarantee <= 30 Hz total control budget)')
    p.add_argument('--strum-guard', action='store_true', help='protect against accidental triggers while strumming or picking')
    p.add_argument('--strum-zone', help='custom strum bounding box ymin,xmin,ymax,xmax (default: 0.50,0.20,1.00,0.85)')
    p.add_argument('--dual-axis', action='store_true', default=True,
                   help='elevation controls filter, knuckle roll controls reverb (default: True)')
    p.add_argument('--hud', action='store_true', help='render ASCII stage HUD in terminal')
    p.add_argument('--no-overlay', action='store_true')
    p.add_argument('--dry-run', action='store_true', help='Validate and print events without UDP')
    p.add_argument('--hand-view-port', type=int, default=47802)
    p.add_argument('--no-hand-view', action='store_true', help='disable local dashboard landmark feed')
    args = p.parse_args()

    if not math.isfinite(args.max_hand_jump) or not 0 < args.max_hand_jump <= 1:
        p.error('--max-hand-jump must be finite and in (0, 1]')
    if not math.isfinite(args.pair_rate) or not 0 < args.pair_rate <= 15:
        p.error('--pair-rate must be finite and in (0, 15] to respect total event budget')

    strum_rect = None
    if args.strum_zone:
        try:
            parts = [float(x.strip()) for x in args.strum_zone.split(',')]
            if len(parts) != 4:
                raise ValueError
            strum_rect = Rect(*parts)
        except Exception:
            p.error('--strum-zone requires 4 comma-separated numbers: ymin,xmin,ymax,xmax in [0,1]')

    import cv2
    import mediapipe as mp
    from jsonschema import Draft202012Validator

    controller = DualAxisController(pair_rate=args.pair_rate)
    strum_guard = StrumGuard(strum_zone=strum_rect) if (args.strum_guard or args.strum_zone) else None
    hud = StageHUD(enabled=args.hud)

    schema = json.loads((Path(__file__).resolve().parents[1] / 'protocol/control.schema.json').read_text())
    validator = Draft202012Validator(schema)
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=args.model),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2,
        min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6)
    cap = cv2.VideoCapture(args.video if args.video else args.camera)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError('Cannot open camera/video')
    fps = cap.get(cv2.CAP_PROP_FPS)
    if args.video and (not math.isfinite(fps) or fps <= 0):
        cap.release()
        raise ValueError('Recorded video must report a positive frame rate')

    start = time.monotonic()
    selector = HandSelector(max_jump=args.max_hand_jump)
    frame_number = count = 0
    last_stamp = -1
    last_sent = minimum_interval = None
    hand_view = None if args.no_hand_view else HandView(args.hand_view_port).start()
    hand_view_error_reported = False

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
            while True:
                ok, frame = cap.read()
                if not ok:
                    if not args.video:
                        raise RuntimeError('Camera disconnected or frame capture failed')
                    break
                if args.video:
                    time.sleep(max(0, start + frame_number / fps - time.monotonic()))
                now = time.monotonic()
                stamp = max(last_stamp + 1, int((now - start) * 1000))
                last_stamp = stamp
                frame_number += 1
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
                y = pinch = None
                confidence = 0.
                centers = [(hand[0].x, hand[0].y) for hand in result.hand_landmarks]
                selected = selector.select(centers)
                points = None
                orientation = None
                zone_status = 'no_hand'
                if selected is not None:
                    points = result.hand_landmarks[selected]
                    height, width = frame.shape[:2]
                    distance = lambda a, b: math.hypot((points[a].x - points[b].x) * width, (points[a].y - points[b].y) * height)
                    scale = distance(5, 17)
                    if scale > 1:
                        y = points[0].y
                        pinch = distance(4, 8) / scale
                        confidence = result.handedness[selected][0].score

                    orientation = compute_hand_orientation(points, width=width, height=height)
                    zone_status = 'expression_zone'
                    if strum_guard and y is not None:
                        suppressed, zone_status = strum_guard.update(x=points[0].x, y=points[0].y, now=now)
                        if suppressed:
                            y = pinch = None
                            controller.rearm()

                    if not args.no_overlay:
                        for point in points:
                            cv2.circle(frame, (int(point.x * width), int(point.y * height)), 3, (0, 255, 0), -1)

                events = controller.update(y, pinch, orientation, confidence, now, int(time.time() * 1000))

                if hand_view:
                    if hand_view.error and not hand_view_error_reported:
                        import sys
                        print('Hand view unavailable: ' + hand_view.error, file=sys.stderr)
                        hand_view_error_reported = True
                    landmarks = [[min(1., max(0., p.x)), min(1., max(0., p.y))] for p in points] if (points and y is not None) else []
                    hand_view.publish(dict(version=1, type='hand', timestamp_ms=int(time.time() * 1000),
                        present=y is not None, engaged=controller.active, confidence=confidence,
                        control=None, value=controller.primary_val, landmarks=landmarks))

                for event in events:
                    validator.validate(event)
                    payload = json.dumps(event, separators=(',', ':'))
                    if args.dry_run:
                        print(payload, flush=True)
                    else:
                        sock.sendto(payload.encode(), (args.host, args.port))
                    count += 1
                    emitted = time.monotonic()
                    if last_sent is not None:
                        interval = emitted - last_sent
                        minimum_interval = interval if minimum_interval is None else min(minimum_interval, interval)
                    last_sent = emitted

                if args.hud:
                    fps_val = count / max(time.monotonic() - start, 0.001)
                    hud_text = hud.update(
                        armed=controller.armed,
                        active=controller.active,
                        zone_status=zone_status,
                        primary_name='filter',
                        primary_val=controller.primary_val,
                        secondary_name='reverb',
                        secondary_val=controller.secondary_val,
                        event_count=count,
                        fps=fps_val,
                    )
                    if hud_text:
                        print(hud_text)

                if not args.no_overlay:
                    p_val_str = f"{controller.primary_val:.2f}" if controller.primary_val is not None else "None"
                    s_val_str = f"{controller.secondary_val:.2f}" if controller.secondary_val is not None else "None"
                    label = f"FILTER: {p_val_str} | REVERB: {s_val_str} active={controller.active} events={count}"
                    cv2.putText(frame, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 255, 255), 1)

                    if strum_guard:
                        z_color = (0, 0, 255) if zone_status in ('strum_zone', 'strum_motion') else (0, 165, 255)
                        cv2.rectangle(frame, (int(strum_guard.strum_zone.xmin * width), int(strum_guard.strum_zone.ymin * height)),
                                      (int(strum_guard.strum_zone.xmax * width), int(strum_guard.strum_zone.ymax * height)), z_color, 1)
                        if zone_status in ('strum_zone', 'strum_motion'):
                            cv2.putText(frame, 'STRUM GUARD: MUTED', (10, 50), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)

                    if orientation:
                        tilt_lbl = f'TILT: {orientation.roll_deg:+.0f} deg ({orientation.tilt_amount*100:.0f}%)'
                        cv2.putText(frame, tilt_lbl, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 200, 0), 1)

                    cv2.imshow('OmniRiff Spatial - q quits; open hand then pinch', frame)
                    key = cv2.waitKey(1) & 0xff
                    if key == ord('q'):
                        break
    finally:
        if hand_view:
            hand_view.close()
        cap.release()
        cv2.destroyAllWindows()
        elapsed = time.monotonic() - start
        import sys
        print(json.dumps(dict(events=count, elapsed_seconds=elapsed, average_hz=count / max(elapsed, .001),
                              minimum_interval_seconds=minimum_interval)), file=sys.stderr)


if __name__ == '__main__':
    main()
