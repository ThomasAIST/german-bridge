// The proxy must receive the complete backend URL in its `url` query value.
window.GB_CONFIG = {
  API_PROXY_URL: 'https://corsproxy.io/?key=dfa5a403&url=',
  API_TARGET_URL: 'http://ec2-54-252-248-255.ap-southeast-2.compute.amazonaws.com:3000',
  // Socket.IO needs a WebSocket-capable HTTPS endpoint; corsproxy.io is not one.
  SOCKET_URL: '',
};
