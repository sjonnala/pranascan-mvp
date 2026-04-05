package com.pranapulse.core.infrastructure.security;

import com.pranapulse.core.audit.infrastructure.AuditLoggingFilter;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            CoreJwtAuthenticationConverter jwtAuthenticationConverter,
            AuditLoggingFilter auditLoggingFilter
    ) throws Exception {
        http
                .csrf(AbstractHttpConfigurer::disable)
                .cors(Customizer.withDefaults())
                .sessionManagement(
                        session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
                )
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/actuator/health", "/actuator/info").permitAll()
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter))
                )
                .addFilterAfter(auditLoggingFilter, BearerTokenAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder(CoreSecurityProperties securityProperties) {
        NimbusJwtDecoder jwtDecoder = NimbusJwtDecoder.withJwkSetUri(
                securityProperties.jwkSetUri()
        ).build();

        OAuth2TokenValidator<Jwt> validator = new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(securityProperties.issuerUri()),
                new AudienceValidator(securityProperties.requiredAudience())
        );
        jwtDecoder.setJwtValidator(validator);
        return jwtDecoder;
    }

    @Bean
    CoreJwtAuthenticationConverter jwtAuthenticationConverter() {
        return new CoreJwtAuthenticationConverter();
    }

    static final class CoreJwtAuthenticationConverter
            implements org.springframework.core.convert.converter.Converter<Jwt, AbstractAuthenticationToken> {

        private final JwtGrantedAuthoritiesConverter scopeConverter =
                new JwtGrantedAuthoritiesConverter();

        @Override
        public AbstractAuthenticationToken convert(Jwt jwt) {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();
            Collection<GrantedAuthority> scopeAuthorities = scopeConverter.convert(jwt);
            if (scopeAuthorities != null) {
                authorities.addAll(scopeAuthorities);
            }
            authorities.addAll(extractRoleAuthorities(jwt));
            authorities.addAll(extractGroupAuthorities(jwt));

            String principalName = Optional.ofNullable(jwt.getClaimAsString("preferred_username"))
                    .orElseGet(() -> Optional.ofNullable(jwt.getClaimAsString("email"))
                            .orElse(jwt.getSubject()));

            return new JwtAuthenticationToken(jwt, authorities, principalName);
        }

        private Collection<GrantedAuthority> extractRoleAuthorities(Jwt jwt) {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();
            Map<String, Object> realmAccess = jwt.getClaimAsMap("realm_access");
            if (realmAccess == null) {
                return authorities;
            }

            Object roles = realmAccess.get("roles");
            if (roles instanceof Collection<?> roleCollection) {
                roleCollection.stream()
                        .filter(String.class::isInstance)
                        .map(String.class::cast)
                        .map(this::toRoleAuthority)
                        .map(SimpleGrantedAuthority::new)
                        .forEach(authorities::add);
            }
            return authorities;
        }

        private Collection<GrantedAuthority> extractGroupAuthorities(Jwt jwt) {
            Set<GrantedAuthority> authorities = new LinkedHashSet<>();
            Collection<String> groups = jwt.getClaimAsStringList("groups");
            if (groups == null) {
                return authorities;
            }

            groups.stream()
                    .map(group -> group.substring(group.lastIndexOf('/') + 1))
                    .filter(group -> !group.isBlank())
                    .map(this::toRoleAuthority)
                    .map(SimpleGrantedAuthority::new)
                    .forEach(authorities::add);
            return authorities;
        }

        private String toRoleAuthority(String value) {
            String normalized = value.trim()
                    .replace('-', '_')
                    .replace(' ', '_')
                    .toUpperCase(Locale.ROOT);
            if (normalized.startsWith("ROLE_")) {
                return normalized;
            }
            return "ROLE_" + normalized;
        }
    }
}
