/**
 * Demo build only: the fixtures were recorded on a fixed school day, so the app's clock starts at that
 * moment and runs forward from there. "Today", the current week and "5 min ago" then match the data.
 */
import { DEMO_NOW } from './meta'

const RealDate = Date
const offset = RealDate.parse(DEMO_NOW) - RealDate.now()

class DemoDate extends RealDate {
  constructor(...args: unknown[]) {
    if (args.length === 0) super(RealDate.now() + offset)
    else if (args.length === 1) super(args[0] as string | number | Date)
    else super(...(args as [number, number, number?, number?, number?, number?, number?]))
  }

  static now(): number {
    return RealDate.now() + offset
  }
}

globalThis.Date = DemoDate as DateConstructor
