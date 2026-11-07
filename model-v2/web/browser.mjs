import {existsSync} from 'node:fs';
import {chromium} from 'playwright';

export function launchBrowser(args = []) {
  const candidates = process.env.CHROME_PATH ? [process.env.CHROME_PATH] :
    ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
  const executablePath = candidates.find(path => existsSync(path));
  if (process.env.CHROME_PATH && !executablePath) {
    throw new Error('CHROME_PATH does not point to an existing browser executable');
  }
  return chromium.launch({headless: true, args, ...(executablePath ? {executablePath} : {})});
}
