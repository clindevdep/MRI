/**
 * Advanced Playwright Stealth Configuration
 * Enhanced browser fingerprinting resistance for MRI Portal
 */

/**
 * Advanced fingerprint randomization
 * Returns realistic browser configuration that changes on each run
 */
export function generateBrowserFingerprint() {
  const viewports = [
    { width: 1920, height: 1080 },
    { width: 1366, height: 768 },
    { width: 1536, height: 864 },
    { width: 1440, height: 900 },
    { width: 1280, height: 720 },
    { width: 2560, height: 1440 },  // 2K
    { width: 3840, height: 2160 }   // 4K
  ];

  const userAgents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
  ];

  const timezones = [
    'America/New_York',
    'America/Chicago',
    'America/Los_Angeles',
    'America/Denver',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin'
  ];

  const locales = [
    'en-US',
    'en-GB',
    'de-DE',
    'fr-FR',
    'es-ES'
  ];

  const viewport = viewports[Math.floor(Math.random() * viewports.length)];
  const userAgent = userAgents[Math.floor(Math.random() * userAgents.length)];
  const timezone = timezones[Math.floor(Math.random() * timezones.length)];
  const locale = locales[Math.floor(Math.random() * locales.length)];

  // Determine color scheme based on time of day (more realistic)
  const hour = new Date().getHours();
  const colorScheme = (hour >= 6 && hour <= 18) ? 'light' : 'dark';

  return {
    viewport,
    userAgent,
    timezone,
    locale,
    colorScheme
  };
}

/**
 * Get enhanced browser launch arguments
 * Disables automation detection and fingerprinting methods
 */
export function getStealthBrowserArgs(viewport) {
  return [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--single-process', // Low-RAM Docker optimization
    '--disable-gpu',
    '--disable-software-rasterizer',

    // Hide automation
    '--disable-blink-features=AutomationControlled',
    '--exclude-switches=enable-automation',
    '--disable-automation',

    // Fingerprint resistance
    '--disable-features=IsolateOrigins,site-per-process',
    '--disable-site-isolation-trials',
    '--disable-features=VizDisplayCompositor',

    // Canvas fingerprinting resistance
    '--disable-canvas-aa',
    '--disable-2d-canvas-clip-aa',
    '--disable-gl-drawing-for-tests',

    // WebGL fingerprinting resistance
    '--use-gl=swiftshader',
    '--disable-webgl',
    '--disable-webgl2',

    // Audio fingerprinting resistance
    '--disable-audio-output',

    // Font fingerprinting resistance
    '--disable-dev-shm-usage',
    '--disable-font-subpixel-positioning',

    // General stealth
    `--window-size=${viewport.width},${viewport.height}`,
    '--lang=en-US,en',
    '--disable-web-security',
    '--disable-features=TranslateUI',
    '--disable-ipc-flooding-protection',

    // Performance
    '--disable-background-networking',
    '--disable-background-timer-throttling',
    '--disable-backgrounding-occluded-windows',
    '--disable-breakpad',
    '--disable-component-extensions-with-background-pages',
    '--disable-extensions',
    '--disable-features=Translate',
    '--disable-hang-monitor',
    '--disable-renderer-backgrounding',
    '--disable-sync',
    '--metrics-recording-only',
    '--mute-audio',
    '--no-first-run'
  ];
}

/**
 * Get realistic HTTP headers that mimic real Chrome browser
 */
export function getRealisticHeaders() {
  return {
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-User': '?1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Ch-Ua': '"Chromium";v="131", "Not_A Brand";v="24"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Cache-Control': 'max-age=0',
    'DNT': '1'
  };
}

/**
 * Inject anti-detection scripts into page context
 * This runs BEFORE any page JavaScript executes
 */
export function getAntiDetectionScript() {
  return () => {
    // Remove webdriver flag
    Object.defineProperty(navigator, 'webdriver', {
      get: () => false,
      configurable: true
    });

    // Override plugins (realistic Chrome plugins)
    Object.defineProperty(navigator, 'plugins', {
      get: () => [
        {
          0: { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' },
          description: 'Portable Document Format',
          filename: 'internal-pdf-viewer',
          length: 1,
          name: 'Chrome PDF Plugin'
        },
        {
          0: { type: 'application/pdf', suffixes: 'pdf', description: '' },
          description: '',
          filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
          length: 1,
          name: 'Chrome PDF Viewer'
        },
        {
          0: { type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable' },
          1: { type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable' },
          description: '',
          filename: 'internal-nacl-plugin',
          length: 2,
          name: 'Native Client'
        }
      ],
      configurable: true
    });

    // Override languages
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
      configurable: true
    });

    // Mock Chrome runtime
    window.chrome = {
      runtime: {},
      loadTimes: function() {},
      csi: function() {},
      app: {}
    };

    // Mock permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
      parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );

    // Override platform if needed (match user agent)
    Object.defineProperty(navigator, 'platform', {
      get: () => 'Win32',
      configurable: true
    });

    // Mock battery API (often checked by fingerprinters)
    Object.defineProperty(navigator, 'getBattery', {
      get: () => () => Promise.resolve({
        charging: true,
        chargingTime: 0,
        dischargingTime: Infinity,
        level: 1,
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => true
      }),
      configurable: true
    });

    // Override screen properties (match viewport)
    Object.defineProperty(screen, 'availWidth', {
      get: () => window.innerWidth,
      configurable: true
    });

    Object.defineProperty(screen, 'availHeight', {
      get: () => window.innerHeight,
      configurable: true
    });

    // Override hardwareConcurrency to realistic value
    Object.defineProperty(navigator, 'hardwareConcurrency', {
      get: () => 8,
      configurable: true
    });

    // Override deviceMemory to realistic value
    Object.defineProperty(navigator, 'deviceMemory', {
      get: () => 8,
      configurable: true
    });

    // Mock connection API
    Object.defineProperty(navigator, 'connection', {
      get: () => ({
        effectiveType: '4g',
        rtt: 50,
        downlink: 10,
        saveData: false
      }),
      configurable: true
    });

    // Remove Playwright-specific properties
    delete window.__playwright;
    delete window.__pw_manual;
    delete window.__PW_inspect;

    // Override toString methods to hide proxying
    const originalToString = Function.prototype.toString;
    Function.prototype.toString = function() {
      if (this === window.chrome.runtime) {
        return 'function () { [native code] }';
      }
      return originalToString.call(this);
    };

    // Randomize canvas fingerprint slightly
    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, attributes) {
      const context = originalGetContext.call(this, type, attributes);

      if (type === '2d') {
        const originalFillText = context.fillText;
        context.fillText = function(text, x, y, maxWidth) {
          // Add tiny random offset to prevent exact fingerprinting
          const noise = Math.random() * 0.0001;
          return originalFillText.call(this, text, x + noise, y + noise, maxWidth);
        };
      }

      return context;
    };

    // Randomize WebGL fingerprint
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
      if (parameter === 37445) {
        return 'Intel Inc.';
      }
      if (parameter === 37446) {
        return 'Intel Iris OpenGL Engine';
      }
      return getParameter.call(this, parameter);
    };
  };
}

/**
 * Apply all stealth measures to a Playwright page
 */
export async function applyStealthToPage(page) {
  // Add init script
  await page.addInitScript(getAntiDetectionScript());

  // Set realistic extra HTTP headers
  await page.setExtraHTTPHeaders(getRealisticHeaders());

  // Emulate timezone and geolocation
  // (Note: geolocation and timezone are set at context level, not page level)
}

/**
 * Create a fully stealthed Playwright browser instance
 */
export async function createStealthBrowser(playwright, options = {}) {
  const fingerprint = generateBrowserFingerprint();

  console.log(`🎭 Fingerprint: ${fingerprint.viewport.width}x${fingerprint.viewport.height}, ${fingerprint.timezone}, ${fingerprint.locale}`);

  const browserArgs = getStealthBrowserArgs(fingerprint.viewport);

  const browserOptions = {
    headless: options.headless !== false,
    args: browserArgs,
    ...options.launchOptions
  };

  // Add proxy if provided
  if (options.proxy) {
    browserOptions.proxy = options.proxy;
  }

  const browser = await playwright.chromium.launch(browserOptions);

  // Enhanced context with realistic settings
  const context = await browser.newContext({
    viewport: fingerprint.viewport,
    userAgent: fingerprint.userAgent,
    locale: fingerprint.locale,
    timezoneId: fingerprint.timezone,
    colorScheme: fingerprint.colorScheme,
    permissions: [],  // Start with no permissions
    extraHTTPHeaders: getRealisticHeaders(),
    // Device scale factor for realism
    deviceScaleFactor: 1,
    isMobile: false,
    hasTouch: false,
    // Realistic geolocation (varies by timezone)
    geolocation: fingerprint.timezone.includes('New_York') ?
      { latitude: 40.7128, longitude: -74.0060 } :
      fingerprint.timezone.includes('London') ?
      { latitude: 51.5074, longitude: -0.1278 } :
      { latitude: 48.8566, longitude: 2.3522 }  // Paris default
  });

  const page = await context.newPage();

  // Apply stealth measures
  await applyStealthToPage(page);

  return { browser, context, page, fingerprint };
}
