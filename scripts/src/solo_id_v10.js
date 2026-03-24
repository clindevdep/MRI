/**
 * Solo ID v10 - Unique Browser Fingerprint Generator
 *
 * Strategy from Plan_SoloID_v10.md:
 * - Each download uses a completely different identity (fingerprint)
 * - Different IP for each download (ProxyScrape rotation)
 * - Different browser fingerprint for each download
 * - Simulate human-like behavior as much as possible
 *
 * Key principle: NO TWO REQUESTS SHOULD LOOK THE SAME
 */

import dotenv from 'dotenv';
dotenv.config(); // Docker provides env vars via compose

/**
 * Generate a completely unique browser fingerprint for each request
 * No caching - every call returns different values
 */
export function generateUniqueFingerprint() {
  const now = new Date();

  // Expanded viewport pool (12 options)
  const viewports = [
    { width: 1280, height: 720 },   // 720p
    { width: 1366, height: 768 },   // Common laptop
    { width: 1440, height: 900 },   // MacBook Air
    { width: 1536, height: 864 },   // 1080p scaled
    { width: 1600, height: 900 },   // 16:9
    { width: 1680, height: 1050 },  // 16:10
    { width: 1920, height: 1080 },  // 1080p
    { width: 1920, height: 1200 },  // 16:10
    { width: 2560, height: 1440 },  // 2K
    { width: 2560, height: 1600 },  // 16:10 2K
    { width: 3440, height: 1440 },  // Ultrawide
    { width: 3840, height: 2160 }   // 4K
  ];

  // User agents paired with matching platforms (each entry: [userAgent, platform])
  const userAgentPlatforms = [
    // Windows (Win32)
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'Win32'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', 'Win32'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Win32'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0', 'Win32'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0', 'Win32'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0', 'Win32'],
    ['Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'Win32'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/117.0.0.0', 'Win32'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Vivaldi/7.0.3495.15', 'Win32'],

    // macOS (MacIntel)
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'MacIntel'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', 'MacIntel'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0', 'MacIntel'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0', 'MacIntel'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15', 'MacIntel'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15', 'MacIntel'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15', 'MacIntel'],

    // Linux (Linux x86_64)
    ['Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'Linux x86_64'],
    ['Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36', 'Linux x86_64'],
    ['Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Linux x86_64'],
    ['Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 'Linux x86_64']
  ];

  // Expanded timezone pool (15 realistic timezones)
  const timezones = [
    'Europe/London',      // UK
    'Europe/Paris',       // France, Germany
    'Europe/Berlin',      // Germany
    'Europe/Madrid',      // Spain
    'Europe/Rome',        // Italy
    'Europe/Amsterdam',   // Netherlands
    'Europe/Brussels',    // Belgium
    'Europe/Warsaw',      // Poland
    'Europe/Stockholm',   // Sweden
    'Europe/Athens',      // Greece
    'America/New_York',   // US East
    'America/Chicago',    // US Central
    'America/Los_Angeles',// US West
    'Asia/Tokyo',         // Japan
    'Australia/Sydney'    // Australia
  ];

  // Expanded locale pool (15 locales matching timezones)
  const locales = [
    'en-GB', 'en-US', 'fr-FR', 'de-DE', 'es-ES',
    'it-IT', 'nl-NL', 'pl-PL', 'sv-SE', 'el-GR',
    'pt-PT', 'pt-BR', 'ja-JP', 'en-AU', 'cs-CZ'
  ];

  // Random selection from pools
  const viewport = viewports[Math.floor(Math.random() * viewports.length)];
  const [userAgent, platform] = userAgentPlatforms[Math.floor(Math.random() * userAgentPlatforms.length)];
  const timezone = timezones[Math.floor(Math.random() * timezones.length)];
  const locale = locales[Math.floor(Math.random() * locales.length)];

  // Time-aware color scheme
  const hours = now.getHours();
  const colorScheme = (hours >= 6 && hours < 22) ? 'light' : 'dark';

  // Random hardware specs
  const hardwareConcurrency = [2, 4, 6, 8, 12, 16][Math.floor(Math.random() * 6)];
  const deviceMemory = [2, 4, 8, 16, 32][Math.floor(Math.random() * 5)];

  // Random screen properties
  const screenDepth = [24, 30, 32][Math.floor(Math.random() * 3)];
  const pixelRatio = [1, 1.25, 1.5, 2][Math.floor(Math.random() * 4)];

  return {
    viewport,
    userAgent,
    timezone,
    locale,
    colorScheme,
    platform,
    hardwareConcurrency,
    deviceMemory,
    screenDepth,
    pixelRatio
  };
}

/**
 * Get random proxy from ProxyScrape for this request
 * Returns null if proxy disabled
 */
export function getProxyConfig() {
  const enableProxy = process.env.ENABLE_PROXY !== 'false';

  if (!enableProxy) {
    return null;
  }

  const username = process.env.PROXYSCRAPE_USERNAME;
  const password = process.env.PROXYSCRAPE_PASSWORD;
  const hostname = process.env.PROXYSCRAPE_HOSTNAME || 'rp.scrapegw.com';
  const port = process.env.PROXYSCRAPE_PORT || '6060';

  if (!username || !password) {
    console.log('⚠️  ProxyScrape credentials not found, proxy disabled');
    return null;
  }

  return {
    server: `http://${hostname}:${port}`,
    username,
    password
  };
}

/**
 * Create a completely unique browser context for each request
 * NO caching, NO reuse - every request is a new identity
 */
export async function createSoloIDBrowser(chromiumModule, options = {}) {
  const fingerprint = generateUniqueFingerprint();
  const proxyConfig = getProxyConfig();

  // Log identity
  console.log(`\n🎭 Solo ID v10 - Unique Identity Generated:`);
  console.log(`   Viewport: ${fingerprint.viewport.width}x${fingerprint.viewport.height}`);
  console.log(`   Timezone: ${fingerprint.timezone}`);
  console.log(`   Locale: ${fingerprint.locale}`);
  console.log(`   Platform: ${fingerprint.platform}`);
  console.log(`   User Agent: ${fingerprint.userAgent.substring(0, 60)}...`);
  if (proxyConfig) {
    console.log(`   Proxy: ${proxyConfig.server} (IP rotates automatically)`);
  } else {
    console.log(`   Proxy: Disabled (direct connection)`);
  }

  // Enhanced browser args to hide automation
  const args = [
    '--disable-blink-features=AutomationControlled',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--single-process', // Low-RAM Docker optimization
    '--disable-setuid-sandbox',
    '--disable-web-security',
    '--disable-features=IsolateOrigins,site-per-process',
    '--allow-running-insecure-content',
    '--disable-webgl',
    '--disable-webgl2',
    '--disable-notifications',
    '--disable-popup-blocking',
    '--ignore-certificate-errors',
    '--ignore-ssl-errors',
    '--disable-gpu',
    '--disable-accelerated-2d-canvas',
    '--disable-accelerated-video-decode',
    `--window-size=${fingerprint.viewport.width},${fingerprint.viewport.height}`,
    `--lang=${fingerprint.locale}`,
    // Random noise in canvas fingerprinting
    '--disable-reading-from-canvas',
    // Disable WebRTC to prevent IP leaks
    '--disable-webrtc',
    '--disable-webrtc-hw-encoding',
    '--disable-webrtc-hw-decoding',
    // Additional fingerprint resistance
    '--disable-features=AudioServiceOutOfProcess',
    '--disable-features=MediaRouter',
    '--disable-default-apps',
    '--disable-extensions',
    '--disable-component-extensions-with-background-pages',
    // Memory
    `--max-old-space-size=${fingerprint.deviceMemory * 256}`
  ];

  // Launch browser with unique configuration
  const launchOptions = {
    headless: options.headless !== false,
    args,
    ...( proxyConfig && { proxy: proxyConfig })
  };

  const browser = await chromiumModule.launch(launchOptions);

  // Create context with unique fingerprint
  const context = await browser.newContext({
    viewport: fingerprint.viewport,
    userAgent: fingerprint.userAgent,
    locale: fingerprint.locale,
    timezoneId: fingerprint.timezone,
    colorScheme: fingerprint.colorScheme,
    deviceScaleFactor: fingerprint.pixelRatio,
    isMobile: false,
    hasTouch: false,
    permissions: [],
    geolocation: undefined, // Don't set location to avoid inconsistency
    extraHTTPHeaders: {
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
      'Accept-Encoding': 'gzip, deflate, br, zstd',
      'Accept-Language': `${fingerprint.locale},en;q=0.9`,
      'DNT': '1',
      'Upgrade-Insecure-Requests': '1',
      'Sec-Fetch-Dest': 'document',
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-Site': 'none',
      'Sec-Fetch-User': '?1',
      'Sec-Ch-Ua': `"Chromium";v="131", "Not_A Brand";v="24"`,
      'Sec-Ch-Ua-Mobile': '?0',
      'Sec-Ch-Ua-Platform': `"${fingerprint.platform.split(' ')[0]}"`
    }
  });

  // Create page
  const page = await context.newPage();

  // Advanced navigator overrides - hide all automation traces
  await page.addInitScript((fp) => {
    // Remove webdriver flag
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined
    });

    // Override platform
    Object.defineProperty(navigator, 'platform', {
      get: () => fp.platform
    });

    // Hardware concurrency
    Object.defineProperty(navigator, 'hardwareConcurrency', {
      get: () => fp.hardwareConcurrency
    });

    // Device memory
    Object.defineProperty(navigator, 'deviceMemory', {
      get: () => fp.deviceMemory
    });

    // Remove Playwright/automation traces
    delete window.__playwright;
    delete window.__pw_manual;
    delete window.__PW_inspect;

    // Mock plugins with realistic values
    Object.defineProperty(navigator, 'plugins', {
      get: () => [
        {
          name: 'Chrome PDF Plugin',
          filename: 'internal-pdf-viewer',
          description: 'Portable Document Format',
          length: 1
        },
        {
          name: 'Chrome PDF Viewer',
          filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
          description: '',
          length: 1
        },
        {
          name: 'Native Client',
          filename: 'internal-nacl-plugin',
          description: '',
          length: 2
        }
      ]
    });

    // Battery API mock
    Object.defineProperty(navigator, 'getBattery', {
      value: () => Promise.resolve({
        charging: true,
        chargingTime: 0,
        dischargingTime: Infinity,
        level: 1.0
      })
    });

    // Connection API
    Object.defineProperty(navigator, 'connection', {
      get: () => ({
        effectiveType: '4g',
        rtt: 50,
        downlink: 10,
        saveData: false
      })
    });

    // Screen properties
    Object.defineProperty(screen, 'colorDepth', {
      get: () => fp.screenDepth
    });
    Object.defineProperty(screen, 'pixelDepth', {
      get: () => fp.screenDepth
    });

    // Canvas fingerprint randomization
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(...args) {
      const ctx = this.getContext('2d');
      if (ctx) {
        // Add tiny random noise (invisible but changes fingerprint)
        const imageData = ctx.getImageData(0, 0, this.width, this.height);
        for (let i = 0; i < imageData.data.length; i += 4) {
          imageData.data[i] += Math.random() * 0.01;     // R
          imageData.data[i+1] += Math.random() * 0.01;   // G
          imageData.data[i+2] += Math.random() * 0.01;   // B
        }
        ctx.putImageData(imageData, 0, 0);
      }
      return originalToDataURL.apply(this, args);
    };

    // WebGL fingerprint randomization
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
      if (param === 37445) { // UNMASKED_VENDOR_WEBGL
        return 'Intel Inc.';
      }
      if (param === 37446) { // UNMASKED_RENDERER_WEBGL
        return 'Intel Iris OpenGL Engine';
      }
      return getParameter.apply(this, arguments);
    };

    // Override function toString to hide proxying
    const originalFunctionToString = Function.prototype.toString;
    Function.prototype.toString = function() {
      if (this === Function.prototype.toString) {
        return 'function toString() { [native code] }';
      }
      return originalFunctionToString.call(this);
    };

    // Permissions API
    const originalQuery = navigator.permissions.query;
    navigator.permissions.query = function(params) {
      if (params.name === 'notifications') {
        return Promise.resolve({ state: 'prompt' });
      }
      return originalQuery.apply(this, arguments);
    };
  }, fingerprint);

  return { browser, context, page, fingerprint };
}

/**
 * Enhanced human behavior - more randomness, more realistic
 */
export async function humanDelay(min = 500, max = 2000) {
  const delay = Math.random() * (max - min) + min;
  // Add occasional long pauses (5% chance)
  const longPause = Math.random() < 0.05 ? Math.random() * 3000 : 0;
  await new Promise(resolve => setTimeout(resolve, delay + longPause));
}

export async function humanMouseMove(page, element) {
  const box = await element.boundingBox();
  if (!box) return;

  // Random target point within element
  const targetX = box.x + box.width * (0.3 + Math.random() * 0.4);
  const targetY = box.y + box.height * (0.3 + Math.random() * 0.4);

  // Current position (start from random position, not 0,0)
  const startX = Math.random() * 500;
  const startY = Math.random() * 300;

  // Move in curved path with 20-40 steps
  const steps = 20 + Math.floor(Math.random() * 20);

  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    // Ease-in-out curve
    const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

    // Add random wandering
    const wanderX = (Math.random() - 0.5) * 50;
    const wanderY = (Math.random() - 0.5) * 50;

    const x = startX + (targetX - startX) * eased + wanderX * (1 - eased);
    const y = startY + (targetY - startY) * eased + wanderY * (1 - eased);

    await page.mouse.move(x, y);
    await new Promise(resolve => setTimeout(resolve, 5 + Math.random() * 15));
  }
}

export async function humanClick(page, selector, options = {}) {
  await humanDelay(200, 700);
  const element = await page.locator(selector).first();

  // Move mouse to element
  await humanMouseMove(page, element);

  // Occasional hesitation before clicking (10% chance)
  if (Math.random() < 0.1) {
    await humanDelay(500, 1500);
  }

  await element.click(options);
  await humanDelay(100, 400);
}

export async function humanType(page, selector, text, options = {}) {
  await humanClick(page, selector);

  // Type character by character with realistic delays
  for (let i = 0; i < text.length; i++) {
    await page.keyboard.type(text[i]);

    // Variable typing speed: 80-250ms per character
    const baseDelay = 80 + Math.random() * 170;

    // Occasional hesitation (8% chance)
    const hesitation = Math.random() < 0.08 ? Math.random() * 500 : 0;

    await new Promise(resolve => setTimeout(resolve, baseDelay + hesitation));
  }
}
