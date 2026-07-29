import { NativeEventEmitter, NativeModules } from 'react-native';

type Endpoint = { endpointId: string; name: string };
type PayloadReceived = { endpointId: string; dataBase64: string };
type ConnectionRequest = {
  endpointId: string;
  name: string;
  authenticationDigits: string;
};

type NearbyNativeModule = {
  start(endpointName: string): Promise<void>;
  stop(): Promise<void>;
  sendPayload(endpointId: string, dataBase64: string): Promise<void>;
  respondToConnection(endpointId: string, accept: boolean): Promise<void>;
  addListener(eventName: string): void;
  removeListeners(count: number): void;
};

const nativeModule = NativeModules.NearbyConnections as
  | NearbyNativeModule
  | undefined;

if (!nativeModule) {
  throw new Error(
    'NearbyConnections native module is not registered. Rebuild the Android app.',
  );
}

const events = new NativeEventEmitter(nativeModule);

export const NearbyConnections = {
  start: (endpointName: string) => nativeModule.start(endpointName),
  stop: () => nativeModule.stop(),
  sendPayload: (endpointId: string, dataBase64: string) =>
    nativeModule.sendPayload(endpointId, dataBase64),
  onEndpointFound: (listener: (endpoint: Endpoint) => void) =>
    events.addListener('endpointFound', listener),
  onEndpointLost: (
    listener: (endpoint: Pick<Endpoint, 'endpointId'>) => void,
  ) => events.addListener('endpointLost', listener),
  onConnected: (listener: (endpoint: Pick<Endpoint, 'endpointId'>) => void) =>
    events.addListener('connected', listener),
  onDisconnected: (
    listener: (endpoint: Pick<Endpoint, 'endpointId'>) => void,
  ) => events.addListener('disconnected', listener),
  onPayloadReceived: (listener: (payload: PayloadReceived) => void) =>
    events.addListener('payloadReceived', listener),
  onConnectionRequested: (listener: (request: ConnectionRequest) => void) =>
    events.addListener('connectionRequested', listener),
  respondToConnection: (endpointId: string, accept: boolean) =>
    nativeModule.respondToConnection(endpointId, accept),
};
