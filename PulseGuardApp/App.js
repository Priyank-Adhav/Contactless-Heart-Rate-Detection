import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';

import HomeScreen from './src/screens/HomeScreen';
import CameraScreen from './src/screens/CameraScreen';
import FingerScreen from './src/screens/FingerScreen';
import ResultsScreen from './src/screens/ResultsScreen';

const Stack = createNativeStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="dark" />
      <Stack.Navigator
        initialRouteName="Home"
        screenOptions={{
          headerStyle: { backgroundColor: '#eef7ee' },
          headerTintColor: '#1b1b2f',
          headerTitleStyle: { fontWeight: '700', fontSize: 17 },
          headerShadowVisible: false,
        }}
      >
        <Stack.Screen name="Home" component={HomeScreen}
          options={{ headerShown: false }} />
        <Stack.Screen name="Camera" component={CameraScreen}
          options={({ route }) => ({
            title: route.params?.forceVisual ? 'Visual Assessment' : 'Face Scan',
          })} />
        <Stack.Screen name="Finger" component={FingerScreen}
          options={{ title: 'Finger Pulse' }} />
        <Stack.Screen name="Results" component={ResultsScreen}
          options={{ title: 'Results', headerBackVisible: false }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
