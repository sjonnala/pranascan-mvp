package com.pranapulse.core.infrastructure.intelligence;

import com.pranapulse.intelligence.grpc.scan.v1.ScanIntelligenceServiceGrpc;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Metadata;
import io.grpc.stub.MetadataUtils;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IntelligenceServiceConfig {

    private static final Metadata.Key<String> INTERNAL_TOKEN_HEADER =
            Metadata.Key.of("x-internal-service-token", Metadata.ASCII_STRING_MARSHALLER);

    @Bean(destroyMethod = "shutdown")
    ManagedChannel intelligenceGrpcChannel(IntelligenceServiceProperties properties) {
        return ManagedChannelBuilder
                .forAddress(properties.grpcHost(), properties.grpcPort())
                .usePlaintext()
                .build();
    }

    @Bean
    ScanIntelligenceServiceGrpc.ScanIntelligenceServiceBlockingStub scanIntelligenceServiceBlockingStub(
            ManagedChannel intelligenceGrpcChannel,
            IntelligenceServiceProperties properties
    ) {
        return ScanIntelligenceServiceGrpc.newBlockingStub(intelligenceGrpcChannel)
                .withInterceptors(MetadataUtils.newAttachHeadersInterceptor(internalTokenMetadata(properties)));
    }
    private static Metadata internalTokenMetadata(IntelligenceServiceProperties properties) {
        Metadata metadata = new Metadata();
        metadata.put(INTERNAL_TOKEN_HEADER, properties.internalToken());
        return metadata;
    }
}
