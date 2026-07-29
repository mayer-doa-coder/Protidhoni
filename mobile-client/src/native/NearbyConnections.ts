import {NativeEventEmitter, NativeModules} from 'react-native';

type Endpoint = {endpointId: string; name: string};

type NearbyNativeModule = {
  start(endpointName: string): Promise<void>;
  stop(): Promise<void>;
  addListener(eventName: string): void;
  removeListeners(count: number): void;
};

const nativeModule = NativeModules.NearbyConnections as NearbyNativeModule | undefined;

if (!nativeModule) {
  throw new Error('NearbyConnections native module is not registered. Rebuild the Android app.');
}

const events = new NativeEventEmitter(nativeModule);

export const NearbyConnections = {
  start: (endpointName: string) => nativeModule.start(endpointName),
  stop: () => nativeModule.stop(),
  onEndpointFound: (listener: (endpoint: Endpoint) => void) => events.addListener('endpointFound', listener),
  onEndpointLost: (listener: (endpoint: Pick<Endpoint, 'endpointId'>) => void) => events.addListener('endpointLost', listener),
};
