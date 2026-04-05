package com.pranapulse.core.consent.web;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ConsentControllerIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void grantConsentAndReadStatusThroughHttpApi() throws Exception {
        MvcResult consentGrant = mockMvc.perform(post("/api/v1/consent")
                        .with(jwt().jwt(jwt -> jwt
                                .subject("oidc-http-user-1")
                                .claim("email", "http-user-1@example.com")
                                .claim("name", "HTTP User 1")))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "consent_version": "1.0",
                                  "purpose": "wellness_screening"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.action").value("granted"))
                .andExpect(jsonPath("$.consent_version").value("1.0"))
                .andReturn();

        JsonNode grantPayload = objectMapper.readTree(consentGrant.getResponse().getContentAsString());
        String userId = grantPayload.get("user_id").asText();

        mockMvc.perform(get("/api/v1/consent/status")
                        .with(jwt().jwt(jwt -> jwt
                                .subject("oidc-http-user-1")
                                .claim("email", "http-user-1@example.com")
                                .claim("name", "HTTP User 1"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user_id").value(userId))
                .andExpect(jsonPath("$.has_active_consent").value(true))
                .andExpect(jsonPath("$.deletion_requested").value(false));
    }
}
