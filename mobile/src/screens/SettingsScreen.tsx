import React, { useState } from 'react';
import { View, Text, Button, StyleSheet, ActivityIndicator, Alert, ScrollView } from 'react-native';
import { revokeConsent, requestDataDeletion } from '../api/pranascanApi';
import ConfirmationModal from '../components/ConfirmationModal';

const SettingsScreen: React.FC = () => {
  const [revokeModalVisible, setRevokeModalVisible] = useState(false);
  const [deletionModalVisible, setDeletionModalVisible] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRevokeConsent = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await revokeConsent();
      Alert.alert('Success', response.message || 'Consent revoked successfully.');
      // DECISION: After consent revocation, the user might need to be logged out
      // or redirected to a different screen. This is out of scope for this task
      // but should be considered for a complete flow.
    } catch (err: any) {
      setError(err.message || 'Failed to revoke consent.');
      Alert.alert('Error', err.message || 'Failed to revoke consent.');
    } finally {
      setIsLoading(false);
      setRevokeModalVisible(false);
    }
  };

  const handleRequestDataDeletion = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await requestDataDeletion();
      Alert.alert('Success', response.message || 'Data deletion request submitted. You have 30 days to cancel.');
      // DECISION: Similar to revocation, user might need feedback about the 30-day hold
      // and how to cancel it. This is currently just a simple alert.
    } catch (err: any) {
      setError(err.message || 'Failed to request data deletion.');
      Alert.alert('Error', err.message || 'Failed to request data deletion.');
    } finally {
      setIsLoading(false);
      setDeletionModalVisible(false);
    }
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Settings</Text>

      {error && <Text style={styles.errorText}>{error}</Text>}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Privacy & Data</Text>
        <Text style={styles.descriptionText}>
          Manage your consent and data preferences here.
        </Text>

        <Button
          title="Revoke Consent"
          onPress={() => setRevokeModalVisible(true)}
          color="#FF6347" // Tomato red for destructive action
          disabled={isLoading}
        />
        <Text style={styles.buttonDescription}>
          Revoking consent will remove your permissions for data collection and processing. This action is irreversible.
        </Text>

        <View style={styles.spacer} />

        <Button
          title="Request Data Deletion (30-day hold)"
          onPress={() => setDeletionModalVisible(true)}
          color="#FF4500" // OrangeRed for another destructive action
          disabled={isLoading}
        />
        <Text style={styles.buttonDescription}>
          Request permanent deletion of all your data. A 30-day hold period applies, during which you can cancel the request.
        </Text>
      </View>

      {isLoading && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#0000ff" />
          <Text style={styles.loadingText}>Processing...</Text>
        </View>
      )}

      <ConfirmationModal
        isVisible={revokeModalVisible}
        title="Confirm Consent Revocation"
        message="Are you sure you want to revoke your consent? This will stop all data collection and processing, and your existing data will be deleted immediately. This action cannot be undone."
        onConfirm={handleRevokeConsent}
        onCancel={() => setRevokeModalVisible(false)}
        confirmText="Revoke Now"
        confirmButtonColor="#FF6347" // This prop is now correctly consumed by ConfirmationModal
        isConfirming={isLoading}
      />

      <ConfirmationModal
        isVisible={deletionModalVisible}
        title="Confirm Data Deletion Request"
        message="Are you sure you want to request permanent deletion of all your data? A 30-day hold period will apply, during which you can cancel the request. After 30 days, your data will be permanently deleted."
        onConfirm={handleRequestDataDeletion}
        onCancel={() => setDeletionModalVisible(false)}
        confirmText="Request Deletion"
        confirmButtonColor="#FF4500" // This prop is now correctly consumed by ConfirmationModal
        isConfirming={isLoading}
      />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    backgroundColor: '#f8f8f8',
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 30,
    textAlign: 'center',
    color: '#333',
  },
  section: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 15,
    marginBottom: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 1.41,
    elevation: 2,
  },
  sectionTitle: {
    fontSize: 22,
    fontWeight: '600',
    marginBottom: 15,
    color: '#555',
  },
  descriptionText: {
    fontSize: 16,
    color: '#666',
    marginBottom: 20,
    lineHeight: 24,
  },
  buttonDescription: {
    fontSize: 14,
    color: '#888',
    marginTop: 8,
    marginBottom: 10,
    lineHeight: 20,
  },
  spacer: {
    height: 20,
  },
  errorText: {
    color: 'red',
    textAlign: 'center',
    marginBottom: 15,
    fontSize: 16,
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(255, 255, 255, 0.8)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 10,
  },
  loadingText: {
    marginTop: 10,
    fontSize: 18,
    color: '#333',
  },
});

export default SettingsScreen;
