module.exports = {
    uiPort: 1880,
    flowFile: "smartcare-flows.json",
    flowFilePretty: true,
    functionGlobalContext: {
        smartcareValidation: require("./validator.cjs").createValidator(
            require(process.env.SMARTCARE_VALIDATION_POLICY || "../../config/validation-policy.json")
        ),
    },
    logging: {console: {level: "info", metrics: false, audit: false}},
    editorTheme: {projects: {enabled: false}},
};
