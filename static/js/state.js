export const state = {
  period: '24h',
  models: [],
  apiKeySet: false,
  testApiKey: '',
  refreshTimer: null,
  dailyData: [],
  allHistory: [],
  historyOffset: 0,
  historyStatus: 'all',
  historySearch: '',
  historyModel: 'all',
  testing: false,
  health: { status: 'unknown', detail: '' },
};

export const REFRESH_INTERVAL = 5000;
export const HISTORY_LIMIT = 12;

export const CONFIG_GROUPS_DEF = [
  { name: 'Connection', icon: 'link', keys: ['TRAE_BASE_URL','BIND_HOST','BIND_PORT','API_KEY','DASHBOARD_PASSWORD','TRAE_EXCLUDE_MODELS'] },
  { name: 'Device',     icon: 'chip', keys: ['TRAE_DEVICE_BRAND','TRAE_DEVICE_CPU','TRAE_DEVICE_TYPE','TRAE_OS_VERSION','TRAE_DEVICE_ID','TRAE_MACHINE_ID'] },
  { name: 'IDE',        icon: 'box',  keys: ['TRAE_APP_ID','TRAE_IDE_VERSION_CODE','TRAE_IDE_VERSION','TRAE_PLUGIN_CHANNEL','TRAE_IDE_TOKEN'] },
];

export const SENSITIVE = new Set(['API_KEY','DASHBOARD_PASSWORD','TRAE_IDE_TOKEN','TRAE_MACHINE_ID','TRAE_DEVICE_ID']);
